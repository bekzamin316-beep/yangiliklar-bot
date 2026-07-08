"""Translation utilities for AI responses."""

import logging

from src.ai_service.summarizer import DashScopeProvider

logger = logging.getLogger(__name__)


class TranslationService:
    """Handles translation of AI responses to Uzbek."""

    def __init__(self):
        self.provider = DashScopeProvider()

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