"""AI-powered digest generator.

Reads original content from sources, deduplicates, merges overlapping events,
sorts by importance, and generates a concise daily digest in Uzbek.
"""

import json
import logging

from src.ai_service.service import AIService
from src.digest.content_fetcher import ContentFetcher

logger = logging.getLogger(__name__)


class DigestGenerator:
    """Generates a concise daily digest from original source content."""

    def __init__(self):
        self.ai_service = AIService()
        self.fetcher = ContentFetcher()

    async def generate(self, news_items: list, source_contents: dict[int, str] | None = None) -> list[dict]:
        """Generate digest items from news items and fetched source content.

        Args:
            news_items: List of News ORM objects from DB (last 24h).
            source_contents: Optional dict {news_id: original_text} from ContentFetcher.

        Returns:
            List of digest item dicts: {text, sentiment, source_link, importance}
        """
        if not news_items:
            return []

        # Build items for AI prompt
        items_for_ai = self._build_items_for_ai(news_items, source_contents)
        if not items_for_ai:
            return []

        try:
            # Use provider digest method (prompt loaded from file)
            ai_response = await self.ai_service.primary.generate_digest(items_for_ai)
            digest_items = self._normalize_items(ai_response)
            # Sort by importance descending
            digest_items.sort(key=lambda x: x.get("importance", 50), reverse=True)
            return digest_items
        except Exception as e:
            logger.error("AI digest generation failed: %s", e)
            return self._fallback_digest(items_for_ai)

    def _build_items_for_ai(self, news_items: list, source_contents: dict[int, str] | None) -> list[dict]:
        """Build normalized list of items for the digest AI prompt."""
        items = []
        for item in news_items:
            item_id = getattr(item, "id", None)
            title = getattr(item, "title", "") or ""
            summary = getattr(item, "analysis", "") or getattr(item, "summary", "") or ""
            sentiment = getattr(item, "sentiment", "neutral") or "neutral"
            importance = getattr(item, "importance_score", 50) or 50
            source_url = getattr(item, "source_url", "") or ""

            # Use fetched original content if available, otherwise DB summary
            original = ""
            if source_contents and item_id is not None and item_id in source_contents:
                original = source_contents[item_id][:1000]
            elif summary:
                original = summary[:500]

            if not title.strip() and not original.strip():
                continue

            items.append({
                "title": title,
                "content": original,
                "sentiment": sentiment,
                "importance": importance,
                "source_url": source_url,
            })
        return items

    def _normalize_items(self, items: list[dict]) -> list[dict]:
        """Validate and normalize digest items from AI response."""
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "") or "").strip()
            if not text:
                continue
            sentiment = str(item.get("sentiment", "neutral") or "neutral").lower().strip()
            if sentiment not in {"bullish", "bearish", "neutral"}:
                sentiment = "neutral"
            try:
                importance = int(item.get("importance", 50) or 50)
            except (TypeError, ValueError):
                importance = 50
            result.append({
                "text": text,
                "sentiment": sentiment,
                "source_link": str(item.get("source_link", "") or "").strip(),
                "importance": max(0, min(100, importance)),
            })
        return result

    def _fallback_digest(self, items: list[dict]) -> list[dict]:
        """Simple fallback when AI fails — deduplicate titles and sort by importance."""
        seen_titles = set()
        result = []
        for item in items:
            title = str(item.get("title", "") or "").strip()
            title_lower = title.lower()[:50]
            if not title or title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)
            result.append({
                "text": title,
                "sentiment": str(item.get("sentiment", "neutral") or "neutral").lower().strip(),
                "source_link": str(item.get("source_url", "") or "").strip(),
                "importance": item.get("importance", 50) or 50,
            })
        result.sort(key=lambda x: x.get("importance", 50), reverse=True)
        return result

    async def close(self) -> None:
        """Clean up resources."""
        await self.fetcher.close()
