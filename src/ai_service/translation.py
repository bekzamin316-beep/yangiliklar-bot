"""Translation utilities for AI responses."""

import logging

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.ai_service.prompt_loader import load_prompt
from src.ai_service.summarizer import DashScopeProvider, OmniRouteProvider, OpenRouterProvider
from src.core.config import settings

logger = logging.getLogger(__name__)


class TranslationService:
    """Handles translation of AI responses to Uzbek — uses the configured AI provider."""

    def __init__(self):
        # Use the same provider chain as analysis so translation keeps working
        # whenever the main AI provider does (previously hardcoded to OmniRoute,
        # which broke when its deepseek-web credentials expired).
        if settings.ai_provider == "openrouter":
            self.provider = OpenRouterProvider()
        elif settings.ai_provider == "omniroute":
            self.provider = OmniRouteProvider()
        else:
            self.provider = DashScopeProvider()
        self.provider.model = settings.ai_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=False,
    )
    async def translate_to_uzbek(self, text: str) -> str:
        """Translate text from any language to Uzbek using AI."""
        if not text.strip():
            return text

        prompt = load_prompt("translate").format(text=text)
        try:
            translated = await self.provider.generate(
                prompt,
                system="Siz professional tarjimon. Barcha tarjimalar o'zbek tilida (Lotin alifbosi) bo'lishi shart.",
            )
            return translated.strip()
        except Exception as e:
            logger.error("Translation failed: %s", e)
            return text