"""Daily Digest repository for database operations."""

from typing import List, Optional
from datetime import datetime, date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.models.digest import DailyDigest
from app.core.database.repositories.base import BaseRepository


class DigestRepository(BaseRepository[DailyDigest]):
    """Repository for DailyDigest model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(DailyDigest, session)

    async def get_by_date(self, digest_date: date) -> Optional[DailyDigest]:
        """Get digest by date."""
        result = await self.session.execute(
            select(DailyDigest).where(
                func.date(DailyDigest.digest_date) == digest_date
            )
        )
        return result.scalar_one_or_none()

    async def get_today_digest(self) -> Optional[DailyDigest]:
        """Get today's digest."""
        return await self.get_by_date(datetime.utcnow().date())

    async def create_or_update_digest(
        self,
        digest_date: datetime,
        news_items: list,
        ai_summary: str = None,
        most_bullish: str = None,
        most_bearish: str = None,
    ) -> DailyDigest:
        """Create new digest or update existing one."""
        existing = await self.get_by_date(digest_date.date())
        
        if existing:
            return await self.update(
                existing.id,
                {
                    "news_count": len(news_items),
                    "news_items": news_items,
                    "ai_summary": ai_summary,
                    "most_bullish": most_bullish,
                    "most_bearish": most_bearish,
                },
            )
        else:
            return await self.create(
                {
                    "digest_date": digest_date,
                    "news_count": len(news_items),
                    "news_items": news_items,
                    "ai_summary": ai_summary,
                    "most_bullish": most_bullish,
                    "most_bearish": most_bearish,
                }
            )

    async def mark_as_published(
        self, digest_id: int, message_id: int, post_url: str
    ) -> Optional[DailyDigest]:
        """Mark digest as published with Telegram details."""
        return await self.update(
            digest_id,
            {
                "is_published": True,
                "telegram_message_id": message_id,
                "telegram_post_url": post_url,
                "published_at": datetime.utcnow(),
            },
        )

    async def get_recent_digests(self, limit: int = 10) -> List[DailyDigest]:
        """Get recent digests."""
        result = await self.session.execute(
            select(DailyDigest)
            .order_by(DailyDigest.digest_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_digest_statistics(self) -> dict:
        """Get digest statistics."""
        total = await self.count()
        
        published_stmt = select(func.count()).select_from(DailyDigest).where(
            DailyDigest.is_published == True
        )
        published_result = await self.session.execute(published_stmt)
        published = published_result.scalar() or 0

        return {
            "total": total,
            "published": published,
        }
