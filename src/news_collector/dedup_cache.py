"""Persistent in-memory dedup cache — survives across scheduler cycles."""

import logging
from datetime import datetime, timezone

from src.core.database import get_session
from src.core.repositories import NewsRepository

logger = logging.getLogger(__name__)


class DedupCache:
    """Cache known hashes and URLs in memory to skip DB lookups.

    Loads all existing hashes/URLs from DB on startup,
    then accumulates new ones as items are processed.
    """

    def __init__(self):
        self._hashes: set[str] = set()
        self._urls: set[str] = set()
        self._loaded = False

    async def load_from_db(self) -> None:
        """Pre-load all existing hashes and URLs from DB."""
        if self._loaded:
            return
        try:
            async with get_session() as session:
                repo = NewsRepository(session)
                rows = await repo.get_all_hashes_and_urls()
            self._hashes = {r[0] for r in rows if r[0]}
            self._urls = {r[1] for r in rows if r[1]}
            self._loaded = True
            logger.info(
                "DedupCache loaded: %d hashes, %d URLs", len(self._hashes), len(self._urls)
            )
        except Exception as e:
            logger.warning("DedupCache load failed, will use DB fallback: %s", e)

    def is_known(self, content_hash: str, url_hash: str) -> bool:
        """Check if item is already known (by hash or URL)."""
        return content_hash in self._hashes or url_hash in self._urls

    def add(self, content_hash: str, url_hash: str) -> None:
        """Mark a new item as known."""
        self._hashes.add(content_hash)
        self._urls.add(url_hash)

    async def check_or_add(self, content_hash: str, url_hash: str) -> bool:
        """Check cache first, then DB. Returns True if duplicate."""
        if self.is_known(content_hash, url_hash):
            return True
        # Fallback: check DB
        async with get_session() as session:
            repo = NewsRepository(session)
            existing = await repo.get_by_hash(content_hash)
            if existing:
                self.add(content_hash, url_hash)
                return True
        return False
