"""RSS feed parser using feedparser with async support."""

import asyncio
import logging
from datetime import datetime, timezone

import feedparser

from src.news_collector.models import RawNewsItem

logger = logging.getLogger(__name__)


class RSSParser:
    """Parse RSS/Atom feeds and extract raw news items."""

    @staticmethod
    async def fetch_feed(url: str, source_name: str, max_entries: int = 20) -> list[RawNewsItem]:
        """Fetch and parse a single RSS feed.

        Runs feedparser in a thread pool to avoid blocking the event loop.
        """
        loop = asyncio.get_running_loop()

        def _parse():
            try:
                feed = feedparser.parse(url)
                if feed.bozo and not feed.entries:
                    logger.warning("RSS feed parse error: %s — %s", url, feed.bozo_exception)
                    return []

                items: list[RawNewsItem] = []
                for entry in feed.entries[:max_entries]:
                    # Extract published date
                    published_at = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        import email.utils
                        try:
                            ts = email.utils.mktime_tz(entry.published_parsed)
                            published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                        except Exception:
                            pass

                    # Extract image URL from media:content or enclosure
                    image_url = None
                    media_content = entry.get("media_content", [])
                    if isinstance(media_content, list) and media_content:
                        for mc in media_content:
                            if isinstance(mc, dict):
                                image_url = mc.get("url")
                                break
                    elif media_content:
                        image_url = media_content.get("url") if hasattr(media_content, "get") else None
                    
                    media_thumbnail = entry.get("media_thumbnail", [])
                    if not image_url and isinstance(media_thumbnail, list) and media_thumbnail:
                        mt = media_thumbnail[0]
                        if isinstance(mt, dict):
                            image_url = mt.get("url")

                    # Build summary from content or description
                    content = ""
                    if entry.get("summary"):
                        content = entry.summary
                    elif entry.get("content"):
                        content_list = entry.content
                        if isinstance(content_list, list) and len(content_list) > 0:
                            c = content_list[0]
                            if hasattr(c, "value"):
                                content = c.value
                            elif isinstance(c, str):
                                content = c
                        elif isinstance(entry.content, str):
                            content = entry.content

                    items.append(RawNewsItem(
                        title=entry.get("title", "Untitled"),
                        content=content,
                        url=entry.get("link", ""),
                        source_name=source_name,
                        published_at=published_at,
                        image_url=image_url,
                        author=entry.get("author"),
                        tags=[t.term for t in entry.get("tags", [])],
                    ))

                return items

            except Exception as e:
                logger.error("Error parsing RSS feed %s: %s", url, e)
                return []

        return await loop.run_in_executor(None, _parse)

    @staticmethod
    async def fetch_all_feeds(
        feeds: list[tuple[str, str]], max_entries: int = 20
    ) -> list[RawNewsItem]:
        """Fetch multiple RSS feeds in parallel.

        Args:
            feeds: List of (url, source_name) tuples.
            max_entries: Max items per feed.

        Returns:
            Deduplicated list of raw news items.
        """
        tasks = [
            RSSParser.fetch_feed(url, name, max_entries)
            for url, name in feeds
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: list[RawNewsItem] = []
        seen_hashes = set()

        for result in results:
            if isinstance(result, Exception):
                logger.error("Feed fetch error: %s", result)
                continue
            for item in result:
                h = item.content_hash()
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    all_items.append(item)

        logger.info("Collected %d unique items from %d feeds", len(all_items), len(feeds))
        return all_items
