"""Prompt loader — loads external prompt templates from src/ai_service/prompts/."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_prompt_cache: dict[str, str] = {}

_custom_analysis_prompt: str | None = None


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory.

    Args:
        name: Prompt file name (e.g. "analyze", "digest", "translate").
              The .txt extension is optional.

    Returns:
        The prompt text. Raises FileNotFoundError if not found.
    """
    if not name.endswith(".txt"):
        filename = f"{name}.txt"
    else:
        filename = name

    if filename not in _prompt_cache:
        path = _PROMPTS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        _prompt_cache[filename] = path.read_text(encoding="utf-8")

    return _prompt_cache[filename]


def get_analysis_prompt() -> str:
    """Return the analysis prompt template (custom override or default file)."""
    if _custom_analysis_prompt:
        return _custom_analysis_prompt
    return load_prompt("analyze")


def set_analysis_prompt(prompt: str) -> None:
    """Set a custom analysis prompt (called from admin panel)."""
    global _custom_analysis_prompt
    _custom_analysis_prompt = prompt
