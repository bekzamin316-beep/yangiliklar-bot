"""News Processor — bridges collector → AI → DB → Publisher."""

import logging
import re

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
        # Use AI-translated title if available; otherwise keep original
        title_uz = analysis.title_uz.strip() if analysis.title_uz else item.title
        if not title_uz:
            title_uz = item.title

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
        }.get(getattr(news, "sentiment", "neutral"), "⚪")

        title = (getattr(news, "title", "") or "").strip()
        summary = (getattr(news, "summary", "") or "").strip()
        analysis = (getattr(news, "analysis", "") or "").strip()
        source = (getattr(news, "source_name", "") or "").strip()
        url = (getattr(news, "source_url", "") or "").strip()

        # Fallbacks so we never publish empty sections
        if not title:
            title = "Yangilik"
        if not summary:
            summary = title

        lines: list[str] = []
        lines.append(f"{sentiment_emoji} <b>{title}</b>")
        lines.append("")
        lines.append(summary)

        if analysis:
            lines.append("")
            lines.append(f"📋 Batafsil tahlil")
            lines.append("")
            lines.append(analysis)

        if url:
            lines.append("")
            lines.append("🔗 Manba")
            lines.append("")
            lines.append(url)

        if source:
            lines.append("")
            lines.append(f"📰 {source}")

        # Hashtags — deduplicated, max 5, case-insensitive, order preserved
        hashtags = NewsProcessor._build_hashtags(news)
        if hashtags:
            lines.append("")
            lines.append(" ".join(hashtags))

        return "\n".join(lines)

    @staticmethod
    def _build_hashtags(news: object) -> list[str]:
        """Build a deduplicated list of at most 5 hashtags for the post."""
        seen: set[str] = set()
        hashtags: list[str] = []

        def add_tag(tag: str) -> None:
            if not tag:
                return
            normalized = tag.lower().replace(" ", "").replace("-", "").lstrip("#")
            if normalized and normalized not in seen:
                seen.add(normalized)
                hashtags.append(f"#{normalized}")

        # Dynamic AI tags first
        tags_attr = getattr(news, "tags", "") or ""
        for tag in tags_attr.split(","):
            add_tag(tag.strip())

        # Sentiment tags
        sentiment = getattr(news, "sentiment", "neutral") or "neutral"
        if sentiment == "bullish":
            add_tag("bullish")
        elif sentiment == "bearish":
            add_tag("bearish")

        # Default crypto tags (only if not already present)
        for default_tag in ["kripto", "kriptovalyuta", "bitcoin"]:
            add_tag(default_tag)

        # Always include #crypto for broader reach if room
        add_tag("crypto")

        return hashtags[:5]
