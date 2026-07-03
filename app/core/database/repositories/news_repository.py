"""News repository for database operations."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.models.news import News, NewsSource, RSSSource
from app.core.database.repositories.base import BaseRepository


class NewsRepository(BaseRepository[News]):
    """Repository for News model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(News, session)

    async def get_by_hash(self, hash_value: str) -> Optional[News]:
        """Get news by hash to check for duplicates."""
        result = await self.session.execute(
            select(News).where(News.hash == hash_value)
        )
        return result.scalar_one_or_none()

    async def get_recent_hashes(self, hours: int = 24) -> List[str]:
        """Get hashes of recent news for duplicate detection."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(News.hash).where(News.created_at >= cutoff_time)
        )
        return [row[0] for row in result.all()]

    async def get_unpublished(self, limit: int = 10) -> List[News]:
        """Get unpublished news items."""
        result = await self.session.execute(
            select(News)
            .where(News.is_published == False)
            .where(News.is_duplicate == False)
            .order_by(News.importance_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_as_published(
        self, news_id: int, message_id: int, post_url: str
    ) -> Optional[News]:
        """Mark news as published with Telegram details."""
        return await self.update(
            news_id,
            {
                "is_published": True,
                "telegram_message_id": message_id,
                "telegram_post_url": post_url,
                "published_at": datetime.utcnow(),
            },
        )

    async def get_by_importance(
        self, min_score: float = 0, max_score: float = 100, limit: int = 50
    ) -> List[News]:
        """Get news filtered by importance score."""
        result = await self.session.execute(
            select(News)
            .where(News.importance_score >= min_score)
            .where(News.importance_score <= max_score)
            .where(News.is_published == True)
            .order_by(News.importance_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_today_news(self) -> List[News]:
        """Get all news published today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(News)
            .where(News.created_at >= today_start)
            .where(News.is_published == True)
            .order_by(News.importance_score.desc())
        )
        return list(result.scalars().all())

    async def get_statistics(self) -> Dict[str, Any]:
        """Get news statistics."""
        total = await self.count()
        
        # Published count
        published_stmt = select(func.count()).select_from(News).where(News.is_published == True)
        published_result = await self.session.execute(published_stmt)
        published = published_result.scalar() or 0

        # Duplicates count
        duplicate_stmt = select(func.count()).select_from(News).where(News.is_duplicate == True)
        duplicate_result = await self.session.execute(duplicate_stmt)
        duplicates = duplicate_result.scalar() or 0

        # Today's count
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_stmt = select(func.count()).select_from(News).where(News.created_at >= today_start)
        today_result = await self.session.execute(today_stmt)
        today = today_result.scalar() or 0

        return {
            "total": total,
            "published": published,
            "duplicates": duplicates,
            "today": today,
        }

    async def get_bullish_news(self, limit: int = 5) -> List[News]:
        """Get most bullish news."""
        result = await self.session.execute(
            select(News)
            .where(News.sentiment == "bullish")
            .where(News.is_published == True)
            .order_by(News.importance_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_bearish_news(self, limit: int = 5) -> List[News]:
        """Get most bearish news."""
        result = await self.session.execute(
            select(News)
            .where(News.sentiment == "bearish")
            .where(News.is_published == True)
            .order_by(News.importance_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class NewsSourceRepository(BaseRepository[NewsSource]):
    """Repository for NewsSource model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(NewsSource, session)

    async def get_active_sources(self) -> List[NewsSource]:
        """Get all active news sources."""
        result = await self.session.execute(
            select(NewsSource).where(NewsSource.is_active == True)
        )
        return list(result.scalars().all())


class RSSSourceRepository(BaseRepository[RSSSource]):
    """Repository for RSSSource model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(RSSSource, session)

    async def get_active_feeds(self) -> List[RSSSource]:
        """Get all active RSS feeds."""
        result = await self.session.execute(
            select(RSSSource).where(RSSSource.is_active == True)
        )
        return list(result.scalars().all())

    async def increment_fetch_count(self, source_id: int) -> None:
        """Increment fetch count for a source."""
        source = await self.get(source_id)
        if source:
            await self.update(
                source_id,
                {
                    "fetch_count": source.fetch_count + 1,
                    "last_fetched": datetime.utcnow(),
                    "error_count": 0,
                },
            )

    async def record_error(self, source_id: int, error: str) -> None:
        """Record an error for a source."""
        source = await self.get(source_id)
        if source:
            await self.update(
                source_id,
                {
                    "error_count": source.error_count + 1,
                    "last_error": error,
                },
            )
