"""In-process per-model health tracker for the AI rotation.

Records successes, failures, and temporary cooldowns for every model name
used through AIService / TranslationService so the admin panel can show
which models are erroring and why.
"""

import threading
import time

_lock = threading.Lock()

# model -> {"count": int, "last": str, "at": float, "wall": float}
_errors: dict[str, dict] = {}
# model -> last successful call (monotonic seconds)
_successes: dict[str, float] = {}
# model -> monotonic timestamp until which the model is skipped
_cooldowns: dict[str, float] = {}


def record_success(model: str) -> None:
    """Mark a successful API call for ``model``."""
    with _lock:
        _successes[model] = time.monotonic()
        entry = _errors.get(model)
        if entry:
            entry["last"] = ""
            entry["at"] = 0.0
            entry["wall"] = 0.0


def record_error(model: str, error: str) -> None:
    """Record a failed API call for ``model``."""
    with _lock:
        entry = _errors.setdefault(model, {"count": 0, "last": "", "at": 0.0, "wall": 0.0})
        entry["count"] += 1
        entry["last"] = (error or "").strip()[:300]
        entry["at"] = time.monotonic()
        entry["wall"] = time.time()


def mark_cooldown(model: str, cooldown_seconds: int) -> None:
    """Skip ``model`` for ``cooldown_seconds`` (quota exhausted / rate limited)."""
    with _lock:
        _cooldowns[model] = time.monotonic() + max(1, int(cooldown_seconds))


def get_error(model: str) -> dict | None:
    """Return the error entry for ``model`` if it has one."""
    with _lock:
        entry = _errors.get(model)
        return dict(entry) if entry else None


def get_cooldown_remaining(model: str) -> int:
    """Seconds left in cooldown for ``model`` (0 when none)."""
    with _lock:
        until = _cooldowns.get(model, 0.0)
    return max(0, int(until - time.monotonic()))


def was_successful(model: str) -> bool:
    """True when ``model`` completed at least one call without errors."""
    with _lock:
        return model in _successes
