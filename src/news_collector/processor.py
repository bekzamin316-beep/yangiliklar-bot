"""News Processor — bridges collector → AI → DB → Publisher."""

import logging

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import NewsRepository
from src.ai_service.service import AIService
from src.ai_service.models import NewsAnalysis
from src.news_collector.models import RawNewsItem

logger = logging.getLogger(__name__)


class NewsProcessor:
    """Process raw news: deduplicate, analyze with AI, save to DB."""

    def __init__(self, ai_service: AIService):
        self.ai = ai_service

    async def process_items(self, items: list[RawNewsItem]) -> list:
        """Process a batch of raw news items.

        Flow:
        1. Skip duplicates (by hash)
        2. Analyze with AI
        3. Filter by importance threshold
        4. Save to DB

        Returns:
            List of saved News objects that passed the threshold.
        """
        processed: list = []

        for item in items:
            try:
                # Check duplicate
                async with get_session() as session:
                    repo = NewsRepository(session)
                existing = await self._get_by_hash(item.content_hash())
                if existing:
                    logger.debug("Skipping duplicate: %s", item.title[:50])
                    continue

                # AI analysis
                analysis = await self.ai.analyze_news(item.title, item.content)

                # Filter by importance
                if analysis.importance_score < settings.importance_threshold:
                    logger.debug(
                        "Low importance (%d), skipping: %s",
                        analysis.importance_score, item.title[:50],
                    )
                    continue

                # Save to DB
                news = await self._save_news(item, analysis)
                processed.append(news)
                logger.info(
                    "Processed: %s | score=%d | %s",
                    item.title[:50], analysis.importance_score, analysis.sentiment,
                )

            except Exception as e:
                logger.error("Error processing %s: %s", item.title[:50], e)

        logger.info("Processed %d/%d items", len(processed), len(items))
        return processed

    async def _get_by_hash(self, content_hash: str):
        async with get_session() as session:
            repo = NewsRepository(session)
            return await repo.get_by_hash(content_hash)

    async def _save_news(self, item: RawNewsItem, analysis: NewsAnalysis) -> object:
        # Translate title to Uzbek so posts display Uzbek headline
        title_uz = item.title
        if self.ai.translator:
            try:
                title_uz = await self.ai.translator.translate_to_uzbek(item.title)
            except Exception as e:
                logger.warning("Title translation failed, using original: %s", e)

        async with get_session() as session:
            repo = NewsRepository(session)
            return await repo.create(
                title=title_uz,
                summary=analysis.summary_uz,
                analysis=analysis.analysis_uz,
                content_hash=item.content_hash(),
                source_url=item.url,
                source_name=item.source_name,
                image_url=item.image_url,
                importance_score=analysis.importance_score,
                sentiment=analysis.sentiment,
                tags=",".join(analysis.tags),
                is_published=False,
            )

    @staticmethod
    def format_post(news: object) -> str:
        """Format a news item as a Telegram HTML post in Uzbek."""

        sentiment_emoji = {
            "bullish": "🟢",
            "bearish": "🔴",
            "neutral": "⚪",
        }.get(news.sentiment, "⚪")

        title = news.title
        summary = news.summary or ""
        analysis = news.analysis or ""
        source = news.source_name or ""
        url = news.source_url or ""

        lines = [
            f"{sentiment_emoji} <b>{title}</b>",
            "",
            summary,
        ]

        if analysis:
            lines.extend(["", f"📋 {analysis}"])

        if url:
            lines.extend(["", f"🔗 <a href='{url}'>Manba</a>"])

        if source:
            lines.append(f"\n📰 {source}")

        # Hashtags — fixed crypto tags + dynamic AI tags
        hashtags = ["#kripto", "#kriptovalyuta", "#bitcoin"]
        if news.tags:
            for tag in news.tags.split(","):
                tag = tag.strip().replace(" ", "").lower()
                if tag and tag not in hashtags:
                    hashtags.append(f"#{tag}")
        if news.sentiment == "bullish":
            hashtags.append("#bullish")
        elif news.sentiment == "bearish":
            hashtags.append("#bearish")
        lines.append(f"\n{' '.join(hashtags)}")

        # Signature footer on every post
        if settings.telegram_channel_username:
            lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━━\n📢 https://t.me/{settings.telegram_channel_username}")

        return "\n".join(lines)
