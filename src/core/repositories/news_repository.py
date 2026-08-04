"""News repository with custom query methods."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repositories.base import BaseRepository
from src.models.news import News


class NewsRepository(BaseRepository[News]):
    """Repository for the News model with domain-specific queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(News, session)

    async def get_by_hash(self, content_hash: str) -> Optional[News]:
        """Find news by its content hash (for deduplication)."""
        result = await self.session.execute(
            select(News).where(News.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def get_all_hashes_and_urls(self) -> list[tuple[str | None, str | None]]:
        """Get all content_hashes and source_urls for dedup cache preload."""
        result = await self.session.execute(
            select(News.content_hash, News.source_url)
        )
        return result.all()

    async def get_unpublished(self, limit: int = 20) -> Sequence[News]:
        """Get unpublished news items, ordered by importance (descending)."""
        result = await self.session.execute(
            select(News)
            .where(News.is_published == False)  # noqa: E712
            .order_by(desc(News.importance_score), desc(News.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_unpublished_since(
        self, since: datetime, limit: int = 20
    ) -> Sequence[News]:
        """Get unpublished news created since a timestamp, by importance."""
        result = await self.session.execute(
            select(News)
            .where(
                and_(
                    News.created_at >= since,
                    News.is_published == False,  # noqa: E712
                )
            )
            .order_by(desc(News.importance_score), desc(News.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_recent(
        self, hours: int = 24, limit: int = 50
    ) -> Sequence[News]:
        """Get recent news within the last N hours."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.session.execute(
            select(News)
            .where(News.created_at >= since)
            .order_by(desc(News.importance_score))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_sentiment(self, sentiment: str, limit: int = 20) -> Sequence[News]:
        """Get news items filtered by sentiment."""
        result = await self.session.execute(
            select(News)
            .where(News.sentiment == sentiment)
            .order_by(desc(News.importance_score))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_published_count_today(self) -> int:
        """Count published news today."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count())
            .select_from(News)
            .where(
                and_(
                    News.is_published == True,  # noqa: E712
                    News.created_at >= today,
                )
            )
        )
        return result.scalar_one()

    async def get_stats_summary(self) -> dict:
        """Get summary statistics about news."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        total = await self.count()
        today_count = await self.session.execute(
            select(func.count()).where(News.created_at >= today)
        )
        published = await self.session.execute(
            select(func.count()).where(News.is_published == True)  # noqa: E712
        )
        avg_importance = await self.session.execute(
            select(func.avg(News.importance_score))
        )

        return {
            "total": total,
            "today": today_count.scalar_one() or 0,
            "published": published.scalar_one() or 0,
            "avg_importance": round(avg_importance.scalar_one() or 0, 1),
        }
