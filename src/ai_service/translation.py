"""Translation utilities for AI responses."""

import logging

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.core.config import settings
from src.ai_service.summarizer import DashScopeProvider, OpenRouterProvider

logger = logging.getLogger(__name__)


class TranslationService:
    """Handles translation of AI responses to Uzbek — always uses DashScope for reliability."""

    def __init__(self):
        # Always use DashScope for translation (no rate limits, works reliably)
        self.provider = DashScopeProvider()
        self.provider.model = "qwen-turbo"  # Fast + cheap model for translation

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

        prompt = (
            f"Quyidagi matnni o'zbek tiliga tarjima qiling. "
            f"Matn rus, ingliz yoki boshqa tillarda bo'lishi mumkin. "
            f"Tarjima faqat o'zbek tilida (Lotin alifbosi) bo'lishi kerak. "
            f"Asl matnni qaytarib bermang, faqat tarjima natijasini yozing:\n\n{text}"
        )
        try:
            translated = await self.provider.generate(
                prompt,
                system="Siz professional tarjimon. Barcha tarjimalar o'zbek tilida (Lotin alifbosi) bo'lishi shart.",
            )
            return translated.strip()
        except Exception as e:
            logger.error("Translation failed: %s", e)
            return text