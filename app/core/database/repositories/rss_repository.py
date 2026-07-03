"""RSS repository for database operations."""

from typing import List, Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.models.news import RSSSource
from app.core.database.repositories.base import BaseRepository


class RSSRepository(BaseRepository[RSSSource]):
    """Repository for RSSSource model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(RSSSource, session)

    async def get_active_feeds(self) -> List[RSSSource]:
        """Get all active RSS feeds."""
        result = await self.session.execute(
            select(RSSSource).where(RSSSource.is_active == True)
        )
        return list(result.scalars().all())

    async def get_feed_by_url(self, url: str) -> Optional[RSSSource]:
        """Get RSS feed by URL."""
        result = await self.session.execute(
            select(RSSSource).where(RSSSource.url == url)
        )
        return result.scalar_one_or_none()

    async def add_feed(self, name: str, url: str) -> RSSSource:
        """Add a new RSS feed."""
        existing = await self.get_feed_by_url(url)
        if existing:
            return existing
        
        return await self.create(
            {
                "name": name,
                "url": url,
                "is_active": True,
            }
        )

    async def remove_feed(self, feed_id: int) -> bool:
        """Remove an RSS feed."""
        return await self.delete(feed_id)

    async def toggle_feed(self, feed_id: int) -> Optional[RSSSource]:
        """Toggle feed active status."""
        feed = await self.get(feed_id)
        if feed:
            return await self.update(feed_id, {"is_active": not feed.is_active})
        return None

    async def test_feed(self, feed_id: int) -> dict:
        """Test RSS feed connectivity and return status."""
        feed = await self.get(feed_id)
        if not feed:
            return {"success": False, "error": "Feed not found"}

        try:
            import aiohttp
            import feedparser
            
            async with aiohttp.ClientSession() as session:
                async with session.get(feed.url, timeout=10) as response:
                    if response.status != 200:
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}",
                        }
                    
                    content = await response.text()
                    parsed = feedparser.parse(content)
                    
                    if parsed.entries:
                        return {
                            "success": True,
                            "entries_count": len(parsed.entries),
                            "feed_title": parsed.feed.get("title", "Unknown"),
                        }
                    else:
                        return {
                            "success": False,
                            "error": "No entries found in feed",
                        }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def record_fetch(self, feed_id: int) -> None:
        """Record successful fetch."""
        feed = await self.get(feed_id)
        if feed:
            await self.update(
                feed_id,
                {
                    "fetch_count": feed.fetch_count + 1,
                    "last_fetched": datetime.utcnow(),
                    "error_count": 0,
                },
            )

    async def record_error(self, feed_id: int, error: str) -> None:
        """Record fetch error."""
        feed = await self.get(feed_id)
        if feed:
            await self.update(
                feed_id,
                {
                    "error_count": feed.error_count + 1,
                    "last_error": error,
                },
            )

    async def get_feed_statistics(self) -> dict:
        """Get RSS feed statistics."""
        from sqlalchemy import func
        
        total_feeds = await self.count()
        
        active_stmt = select(func.count()).select_from(RSSSource).where(RSSSource.is_active == True)
        active_result = await self.session.execute(active_stmt)
        active_feeds = active_result.scalar() or 0

        total_fetches_stmt = select(func.sum(RSSSource.fetch_count))
        total_fetches_result = await self.session.execute(total_fetches_stmt)
        total_fetches = total_fetches_result.scalar() or 0

        return {
            "total_feeds": total_feeds,
            "active_feeds": active_feeds,
            "total_fetches": total_fetches,
        }
