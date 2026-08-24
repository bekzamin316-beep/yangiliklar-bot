"""On-demand live probe of every rotation model.

Sends a tiny chat request to each configured model in parallel and classifies
the outcome (OK / model missing / quota exhausted / timeout / other), so the
admin panel can display the exact health of the whole rotation.
"""

import asyncio
import logging

from src.ai_service import model_health
from src.ai_service.summarizer import DashScopeProvider, OmniRouteProvider, OpenRouterProvider
from src.core.config import settings

logger = logging.getLogger(__name__)

PROBE_PROMPT = "Javob sifatida faqat 'OK' so'zini yozing."
PROBE_CONCURRENCY = 8
PROBE_TIMEOUT = 25


def _build_provider():
    """Instantiate the provider matching the resolved AI_PROVIDER."""
    provider = settings.effective_provider
    if provider == "openrouter":
        return OpenRouterProvider()
    if provider == "omniroute":
        return OmniRouteProvider()
    return DashScopeProvider()


def classify_error(error: str) -> str:
    """Map an exception string to a short human-readable label."""
    low = (error or "").lower()
    if "timed out" in low or "timeout" in low:
        return "⏱ Timeout"
    if "400" in error:
        return "Model mavjud emas (400)"
    if "403" in error or "quota" in low:
        return "Limit tugagan (403)"
    if "404" in error:
        return "Xato (404)"
    if "429" in error or "rate limit" in low:
        return "Limit tugagan (429)"
    if "401" in error or "unauthorized" in low or "invalid api key" in low:
        return "API kalit xato (401)"
    return f"Xato ({(error or '').strip()[:50]})"


async def _probe_one(model: str, sem: asyncio.Semaphore) -> tuple[str, bool, str]:
    """Probe a single model with its own provider instance (no shared state)."""
    async with sem:
        provider = _build_provider()
        provider.model = model
        provider.timeout = min(int(getattr(provider, "timeout", 30) or 30), PROBE_TIMEOUT)
        try:
            await provider.generate(PROBE_PROMPT, max_tokens=8)
            model_health.record_success(model)
            logger.info("Probe %s: OK", model)
            return model, True, ""
        except Exception as e:
            label = classify_error(str(e))
            model_health.record_error(model, str(e))
            logger.info("Probe %s: %s", model, label)
            return model, False, label


async def probe_all(models: list[str]) -> dict[str, tuple[bool, str]]:
    """Probe many models concurrently. Returns model -> (ok, error_label)."""
    sem = asyncio.Semaphore(PROBE_CONCURRENCY)
    results = await asyncio.gather(*(_probe_one(m, sem) for m in models))
    return {m: (ok, msg) for m, ok, msg in results}
