"""RSS source repository."""

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repositories.base import BaseRepository
from src.models.news import RSSSource


class RSSSourceRepository(BaseRepository[RSSSource]):
    """Repository for RSS sources."""

    def __init__(self, session: AsyncSession):
        super().__init__(RSSSource, session)

    async def get_active_sources(self) -> Sequence[RSSSource]:
        """Get all active RSS sources."""
        result = await self.session.execute(
            select(RSSSource).where(RSSSource.is_active == True)  # noqa: E712
        )
        return result.scalars().all()

    async def get_by_url(self, url: str) -> Optional[RSSSource]:
        """Find an RSS source by URL."""
        result = await self.session.execute(
            select(RSSSource).where(RSSSource.url == url)
        )
        return result.scalar_one_or_none()

    async def increment_fetch_count(self, source_id: int) -> bool:
        """Increment fetch counter for a source."""
        source = await self.get_by_id(source_id)
        if source is None:
            return False
        source.fetch_count += 1
        await self.session.commit()
        return True

    async def increment_error_count(self, source_id: int, error: str | None = None) -> bool:
        """Increment error counter for a source."""
        source = await self.get_by_id(source_id)
        if source is None:
            return False
        source.error_count += 1
        if error:
            source.last_error = error
        await self.session.commit()
        return True

    async def seed_sources(self, urls: list[str]) -> None:
        """Seed RSS sources from a list of URLs. Skips existing URLs."""
        name_map = {
            "coindesk": "CoinDesk",
            "cointelegraph": "CoinTelegraph",
            "binance": "Binance Announcements",
            "bybit": "Bybit Blog",
            "okx": "OKX",
            "kucoin": "KuCoin",
            "cryptopotato": "CryptoPotato",
            "crypto-news-flash": "Crypto News Flash",
            "bitcoinmagazine": "Bitcoin Magazine",
        }

        # Normalize and deduplicate input URLs
        seen: set[str] = set()
        unique_urls: list[str] = []
        for url in urls:
            normalized = url.strip().rstrip("/")
            if normalized not in seen:
                seen.add(normalized)
                unique_urls.append(url.strip())

        if not unique_urls:
            return

        # Build insert payloads
        values = []
        for url in unique_urls:
            name = url
            for keyword, display_name in name_map.items():
                if keyword in url.lower().replace("-", ""):
                    name = display_name
                    break
            values.append({"name": name, "url": url, "is_active": True})

        if not values:
            return

        try:
            # Use dialect-specific upsert to ignore duplicate URLs safely
            dialect = self.session.bind.dialect.name
            if dialect == "sqlite":
                stmt = sqlite_insert(RSSSource).values(values)
            elif dialect == "postgresql":
                stmt = pg_insert(RSSSource).values(values)
            else:
                # Fallback for other dialects: skip manually and add in bulk
                existing_result = await self.session.execute(
                    select(RSSSource.url).where(
                        RSSSource.url.in_([v["url"] for v in values])
                    )
                )
                existing_urls = {row[0] for row in existing_result.all()}
                values = [v for v in values if v["url"] not in existing_urls]
                if not values:
                    return
                self.session.add_all([RSSSource(**v) for v in values])
                await self.session.commit()
                return

            await self.session.execute(
                stmt.on_conflict_do_nothing(index_elements=["url"])
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
