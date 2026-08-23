"""Translation utilities for AI responses."""

import logging

from src.ai_service.prompt_loader import load_prompt
from src.ai_service.summarizer import DashScopeProvider, OmniRouteProvider, OpenRouterProvider
from src.core.config import settings

logger = logging.getLogger(__name__)


class TranslationService:
    """Handles translation of AI responses to Uzbek — uses the configured AI provider.

    The provider and model chain mirrors the analysis chain: primary → backup →
    any other provider that has valid credentials (e.g. DashScope when OpenRouter
    is rate-limited). Each provider tries its model(s) in turn, so a single
    dead/rate-limited model or key can never silently break translations again.
    """

    def __init__(self):
        # Order of preference: configured primary → configured backup → any
        # other provider with valid credentials. Providers without a key are
        # skipped, and duplicates are collapsed.
        names = [settings.ai_provider]
        if settings.ai_backup_provider and settings.ai_backup_provider not in names:
            names.append(settings.ai_backup_provider)
        for candidate in ("dashscope", "openrouter"):
            if candidate not in names:
                names.append(candidate)
        # OmniRoute is self-hosted with optional auth — only auto-add it when
        # explicitly keyed, so a dead/unconfigured router never adds latency.
        if settings.omniroute_api_key and "omniroute" not in names:
            names.append("omniroute")

        self.providers: list = []
        for name in names:
            provider = self._build_provider(name)
            if provider and all(type(p) is not type(provider) for p in self.providers):
                self.providers.append(provider)

    @staticmethod
    def _build_provider(provider_name: str):
        """Instantiate a provider by name, or None when it lacks credentials."""
        if provider_name == "openrouter":
            if not settings.openrouter_api_key:
                return None
            return OpenRouterProvider()
        if provider_name == "omniroute":
            return OmniRouteProvider()
        if provider_name == "dashscope":
            if not settings.dashscope_api_key:
                return None
            return DashScopeProvider()
        return None

    @staticmethod
    def _models_for(provider) -> list[str]:
        """Return the model(s) to try for a given provider."""
        if isinstance(provider, DashScopeProvider):
            return [settings.ai_model_backup or "qwen-plus"]
        if isinstance(provider, OmniRouteProvider):
            return [settings.ai_model_backup or settings.ai_model]
        return settings.ai_models_list or [settings.ai_model]

    async def translate_to_uzbek(self, text: str) -> str:
        """Translate text from any language to Uzbek using AI.

        Falls back across the configured providers and models. Returns the
        original text when every provider fails so the caller never crashes.
        """
        if not text.strip():
            return text

        # Use replace() instead of .format() so translated text containing
        # braces (e.g. JSON, code) never crashes the prompt builder.
        prompt = load_prompt("translate").replace("{text}", text)
        system = "Siz professional tarjimon. Barcha tarjimalar o'zbek tilida (Lotin alifbosi) bo'lishi shart."

        for i, provider in enumerate(self.providers):
            for model in self._models_for(provider):
                try:
                    provider.model = model
                    translated = await provider.generate(prompt, system=system)
                    result = translated.strip()
                    if result:
                        return result
                except Exception as e:
                    logger.warning(
                        "Translation provider %d/%d (%s, model %s) failed: %s",
                        i + 1, len(self.providers), type(provider).__name__, model, e,
                    )

        logger.error("All translation providers failed for text: %s", text[:80])
        return text

    async def warmup_check(self) -> bool:
        """Health check — verifies at least one provider can translate."""
        test = "test"
        result = await self.translate_to_uzbek(test)
        return result.lower() != "test"
