"""RSS news collector service."""

import feedparser
import hashlib
from typing import List, Dict, Optional
from datetime import datetime, timezone
import aiohttp
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """Represents a news item from RSS feed."""
    title: str
    summary: str
    link: str
    source_name: str
    published_at: datetime
    content_hash: str


class RSSCollector:
    """Collects news from RSS feeds."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"User-Agent": "Mozilla/5.0 (compatible; CryptoNewsBot/1.0)"}
            )
        return self.session

    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def _generate_hash(self, title: str, content: str) -> str:
        """Generate hash for duplicate detection."""
        content_str = f"{title}:{content}"
        return hashlib.sha256(content_str.encode()).hexdigest()

    def _parse_date(self, date_str: str) -> datetime:
        """Parse RSS date string to datetime."""
        if not date_str:
            return datetime.now(timezone.utc)
        
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            try:
                from dateutil import parser
                return parser.parse(date_str)
            except Exception:
                return datetime.now(timezone.utc)

    async def fetch_feed(self, url: str, source_name: str) -> List[NewsItem]:
        """Fetch news from a single RSS feed."""
        news_items = []
        
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch {url}: {response.status}")
                    return news_items
                
                content = await response.text()
                feed = feedparser.parse(content)
                
                for entry in feed.entries[:20]:  # Limit to 20 latest entries
                    title = getattr(entry, 'title', 'No Title')
                    summary = getattr(entry, 'summary', getattr(entry, 'description', ''))
                    link = getattr(entry, 'link', '')
                    
                    if not link:
                        continue
                    
                    published_at = self._parse_date(
                        getattr(entry, 'published', getattr(entry, 'updated', ''))
                    )
                    
                    content_hash = self._generate_hash(title, summary)
                    
                    news_items.append(NewsItem(
                        title=title,
                        summary=summary,
                        link=link,
                        source_name=source_name,
                        published_at=published_at,
                        content_hash=content_hash
                    ))
                
                logger.info(f"Fetched {len(news_items)} items from {source_name}")
                
        except Exception as e:
            logger.error(f"Error fetching feed {url}: {e}")
        
        return news_items

    async def collect_all(self, sources: List[Dict[str, str]]) -> List[NewsItem]:
        """Collect news from all sources."""
        all_news = []
        
        tasks = [
            self.fetch_feed(source['url'], source['name'])
            for source in sources
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_news.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Collection task failed: {result}")
        
        # Sort by published date, newest first
        all_news.sort(key=lambda x: x.published_at, reverse=True)
        
        return all_news

    async def collect_from_urls(self, urls: List[str]) -> List[NewsItem]:
        """Collect news from list of URLs."""
        sources = []
        for url in urls:
            # Extract source name from URL
            source_name = url.split('//')[-1].split('/')[0].replace('www.', '')
            sources.append({'url': url, 'name': source_name})
        
        return await self.collect_all(sources)


# Import asyncio for gather
import asyncio

__all__ = ["RSSCollector", "NewsItem"]
