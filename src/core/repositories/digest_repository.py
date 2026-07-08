"""Digest and log repositories."""

from datetime import date, datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repositories.base import BaseRepository
from src.models.digest import DailyDigest
from src.models.log import SystemLog


class DigestRepository(BaseRepository[DailyDigest]):
    """Repository for daily digests."""

    def __init__(self, session: AsyncSession):
        super().__init__(DailyDigest, session)

    async def get_by_date(self, digest_date: date) -> Optional[DailyDigest]:
        """Get digest for a specific date."""
        result = await self.session.execute(
            select(DailyDigest).where(DailyDigest.digest_date == digest_date)
        )
        return result.scalar_one_or_none()

    async def get_recent(self, limit: int = 10) -> Sequence[DailyDigest]:
        """Get recent digests."""
        result = await self.session.execute(
            select(DailyDigest)
            .order_by(desc(DailyDigest.digest_date))
            .limit(limit)
        )
        return result.scalars().all()


class LogRepository(BaseRepository[SystemLog]):
    """Repository for system logs."""

    def __init__(self, session: AsyncSession):
        super().__init__(SystemLog, session)

    async def get_recent(self, limit: int = 50, level: str | None = None) -> Sequence[SystemLog]:
        """Get recent log entries."""
        query = select(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit)
        if level:
            query = query.where(SystemLog.level == level)
        result = await self.session.execute(query)
        return result.scalars().all()
