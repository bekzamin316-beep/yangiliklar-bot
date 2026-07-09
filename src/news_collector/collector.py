"""News Collector — orchestrates all collection sources."""

import logging
from datetime import datetime, timezone

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import NewsRepository, RSSSourceRepository
from src.news_collector.models import RawNewsItem
from src.news_collector.rss_parser import RSSParser
from src.news_collector.news_scraper import CryptoPanicScraper

logger = logging.getLogger(__name__)


class NewsCollector:
    """Collects raw news from all configured sources."""

    def __init__(self):
        self.rss_parser = RSSParser()
        self.cryptopanic = CryptoPanicScraper()

    async def collect_all(self) -> list[RawNewsItem]:
        """Collect news from all sources and return deduplicated items."""
        all_items: list[RawNewsItem] = []
        seen_hashes = set()
        seen_urls = set()

        # 1. RSS feeds
        rss_items = await self._collect_rss()
        for item in rss_items:
            h = item.content_hash()
            uh = item.url_hash()
            if h not in seen_hashes and uh not in seen_urls:
                seen_hashes.add(h)
                seen_urls.add(uh)
                all_items.append(item)

        # 2. CryptoPanic API (if configured)
        if settings.cryptopanic_api_key:
            cp_items = await self.cryptopanic.fetch_news(settings.max_news_per_run)
            for item in cp_items:
                h = item.content_hash()
                uh = item.url_hash()
                if h not in seen_hashes and uh not in seen_urls:
                    seen_hashes.add(h)
                    seen_urls.add(uh)
                    all_items.append(item)

        logger.info("Total collected: %d unique news items", len(all_items))
        return all_items

    async def _collect_rss(self) -> list[RawNewsItem]:
        """Collect from all active RSS sources in the DB."""
        async with get_session() as session:
            rss_repo = RSSSourceRepository(session)
            sources = await rss_repo.get_active_sources()

        if not sources:
            logger.warning("No active RSS sources in DB, using .env fallback")
            sources = await self._seed_from_env()

        feeds = [(s.url, s.name) for s in sources]
        raw_items = await self.rss_parser.fetch_all_feeds(
            feeds, max_entries=settings.max_news_per_run
        )

        # Update fetch timestamps
        async with get_session() as session:
            rss_repo = RSSSourceRepository(session)
            now = datetime.now(timezone.utc)
            for source in sources:
                source.last_fetched_at = now
                source.fetch_count += 1
                await session.commit()

        return raw_items

    async def _seed_from_env(self) -> list:
        """Seed RSS sources from .env and return them."""
        from src.models.news import RSSSource

        async with get_session() as session:
            rss_repo = RSSSourceRepository(session)
            await rss_repo.seed_sources(settings.rss_source_list)
            return await rss_repo.get_active_sources()

    async def ensure_sources_seeded(self) -> None:
        """Ensure RSS sources are seeded from .env on startup."""
        async with get_session() as session:
            rss_repo = RSSSourceRepository(session)
            await rss_repo.seed_sources(settings.rss_source_list)
