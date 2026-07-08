"""CryptoPanic API scraper for crypto news."""

import logging
from datetime import datetime, timezone

import httpx

from src.core.config import settings
from src.news_collector.models import RawNewsItem

logger = logging.getLogger(__name__)


class CryptoPanicScraper:
    """Fetch news from CryptoPanic API."""

    BASE_URL = "https://api.cryptopanic.com/api/v1"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.cryptopanic_api_key

    async def fetch_news(self, limit: int = 20) -> list[RawNewsItem]:
        """Fetch latest crypto news from CryptoPanic."""
        if not self.api_key:
            logger.warning("CryptoPanic API key not configured, skipping")
            return []

        items: list[RawNewsItem] = []

        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/news/",
                    params={
                        "authorization": self.api_key,
                        "currencies": "BTC,ETH,SOL,AVAX",
                        "filters[content_types][]": ["analysis", "press-release"],
                        "size": limit,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                for article in data.get("results", [])[:limit]:
                    published_at = None
                    if article.get("published_at"):
                        try:
                            published_at = datetime.fromisoformat(
                                article["published_at"].replace("Z", "+00:00")
                            )
                        except Exception:
                            pass

                    items.append(RawNewsItem(
                        title=article.get("title", "Untitled"),
                        content=article.get("text", ""),
                        url=article.get("url", ""),
                        source_name="CryptoPanic",
                        published_at=published_at,
                        image_url=article.get("image_url"),
                    ))

            except httpx.HTTPError as e:
                logger.error("CryptoPanic API error: %s", e)
            except Exception as e:
                logger.error("CryptoPanic fetch error: %s", e)

        logger.info("CryptoPanic: fetched %d items", len(items))
        return items
