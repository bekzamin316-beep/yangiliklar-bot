"""High-level AI service with retry and fallback support."""

import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.ai_service.models import NewsAnalysis
from src.ai_service.summarizer import DashScopeProvider, OpenRouterProvider
from src.ai_service.translation import TranslationService

logger = logging.getLogger(__name__)


class AIService:
    """AI service wrapper with retry and fallback."""

    def __init__(self):
        # Choose provider based on config
        if settings.ai_provider == "openrouter":
            self.primary = OpenRouterProvider()
        else:
            self.primary = DashScopeProvider()
            
        # Backup provider (if configured)
        if settings.ai_backup_api_key:
            if settings.ai_backup_provider == "openrouter":
                self.backup = OpenRouterProvider()
            else:
                self.backup = DashScopeProvider()
        else:
            self.backup = None
            
        # Translator
        self.translator = TranslationService() if settings.enable_translation else None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def analyze_article(self, title: str, content: str) -> NewsAnalysis:
        """Analyze a news article with retry logic.

        Alias for compatibility — same as analyze_news().
        """
        return await self.analyze_news(title, content)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def analyze_news(self, title: str, content: str) -> NewsAnalysis:
        """Analyze a news article. Falls back to backup provider if primary fails."""
        try:
            analysis = await self.primary.analyze_news(title, content)
            
            # Translate if enabled
            if self.translator and analysis.summary_uz:
                analysis.summary_uz = await self.translator.translate_to_uzbek(analysis.summary_uz)
                analysis.analysis_uz = await self.translator.translate_to_uzbek(analysis.analysis_uz)
                
            return analysis
            
        except Exception as e:
            logger.warning("Primary AI provider failed: %s", e)
            if self.backup:
                try:
                    logger.info("Trying backup AI provider...")
                    analysis = await self.backup.analyze_news(title, content)
                    
                    # Translate if enabled
                    if self.translator and analysis.summary_uz:
                        analysis.summary_uz = await self.translator.translate_to_uzbek(analysis.summary_uz)
                        analysis.analysis_uz = await self.translator.translate_to_uzbek(analysis.analysis_uz)
                        
                    return analysis
                except Exception as e2:
                    logger.error("Backup AI provider also failed: %s", e2)

            # Return minimal analysis so the news is still saved
            logger.warning("Returning minimal analysis for: %s", title[:50])
            fallback_summary = title[:200]
            if self.translator:
                try:
                    fallback_summary = await self.translator.translate_to_uzbek(fallback_summary)
                except Exception as te:
                    logger.error("Fallback translation also failed: %s", te)
            return NewsAnalysis(
                summary_uz=fallback_summary,
                analysis_uz="Yangilik tavsifi mavjud emas.",
                importance_score=50,
                sentiment="neutral",
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def create_digest(self, news_items: list[dict]) -> dict:
        """Generate a daily digest from news items."""
        try:
            digest = await self.primary.generate_digest(news_items)
            
            # Translate if enabled
            if self.translator:
                for key in ["summary", "most_bullish", "most_bearish"]:
                    if digest.get(key):
                        digest[key] = await self.translator.translate_to_uzbek(digest[key])
                        
            return digest
            
        except Exception as e:
            logger.warning("Primary digest generation failed: %s", e)
            if self.backup:
                try:
                    digest = await self.backup.generate_digest(news_items)
                    
                    # Translate if enabled
                    if self.translator:
                        for key in ["summary", "most_bullish", "most_bearish"]:
                            if digest.get(key):
                                digest[key] = await self.translator.translate_to_uzbek(digest[key])
                                
                    return digest
                except Exception as e2:
                    logger.error("Backup digest generation failed: %s", e2)

            return {
                "summary": "Bugun kriptovalyuta bozorida turli xil yangiliklar bo'ldi.",
                "most_bullish": "",
                "most_bearish": "",
            }
