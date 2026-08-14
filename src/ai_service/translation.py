"""Translation utilities for AI responses."""

import logging
import time

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.ai_service.prompt_loader import load_prompt
from src.ai_service.summarizer import DashScopeProvider, OmniRouteProvider, OpenRouterProvider
from src.core.config import settings

logger = logging.getLogger(__name__)


class TranslationService:
    """Handles translation of AI responses to Uzbek — uses the configured AI provider.

    The provider and model are chosen to mirror the analysis chain, and the
    translation request falls back across providers (primary → backup) so a
    single dead model/key can never silently break translations again.
    """

    def __init__(self):
        # Build provider chain in the same order the analysis service uses,
        # skipping providers that lack credentials.
        self.providers: list = []
        primary = self._build_provider(settings.ai_provider)
        if primary:
            self.providers.append(primary)
        backup = self._build_provider(settings.ai_backup_provider or settings.ai_provider)
        if backup and backup.api_key and backup not in self.providers:
            self.providers.append(backup)

        # Model used for translation — prefer the first rotation model (which is
        # what actually works for analysis) over the raw ai_model default.
        self.models = settings.ai_models_list or [settings.ai_model]
        if self.providers:
            self.providers[0].model = self.models[0]
        # Backup provider uses its own model (OmniRoute models differ from OpenRouter)
        if len(self.providers) > 1 and settings.ai_model_backup:
            self.providers[1].model = settings.ai_model_backup

    @staticmethod
    def _build_provider(provider_name: str):
        """Instantiate a provider by name, or None when not configured."""
        if provider_name == "openrouter":
            p = OpenRouterProvider()
        elif provider_name == "omniroute":
            p = OmniRouteProvider()
        elif provider_name == "dashscope":
            p = DashScopeProvider()
        else:
            return None
        return p if p.api_key else None

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=False,
    )
    async def translate_to_uzbek(self, text: str) -> str:
        """Translate text from any language to Uzbek using AI.

        Falls back across the configured providers. Returns the original text
        when every provider fails so the caller never crashes.
        """
        if not text.strip():
            return text

        prompt = load_prompt("translate").format(text=text)
        system = "Siz professional tarjimon. Barcha tarjimalar o'zbek tilida (Lotin alifbosi) bo'lishi shart."

        for i, provider in enumerate(self.providers):
            try:
                translated = await provider.generate(prompt, system=system)
                result = translated.strip()
                if result:
                    return result
            except Exception as e:
                logger.warning(
                    "Translation provider %d/%d failed: %s",
                    i + 1, len(self.providers), e,
                )

        logger.error("All translation providers failed for text: %s", text[:80])
        return text

    async def warmup_check(self) -> bool:
        """Health check — verifies at least one provider can translate."""
        test = "test"
        result = await self.translate_to_uzbek(test)
        return result.lower() != "test"
