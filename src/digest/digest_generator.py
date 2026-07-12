"""AI-powered digest generator.

Reads original content from sources, deduplicates, merges overlapping events,
sorts by importance, and generates a concise daily digest in Uzbek.
"""

import json
import logging

from src.ai_service.service import AIService
from src.digest.content_fetcher import ContentFetcher

logger = logging.getLogger(__name__)

DIGEST_GENERATE_PROMPT = """Siz kunlik kripto yangiliklar digest muallifidir. Quyidagi yangiliklar asosida concise digest tayyorlang.

QOIDALAR:
1. Har bir yangilik FAQAT 1–3 qisqa gapda (o'zbek tilida, Lotin alifbosi) yozing
2. Bir xil voqeaga oid yangiliklar BIRLASHIRING (merge) — bir nechta yangilik bir voqea haqida bo'lsa, faqat bitta item yarating
3. Dublikatlarni OLIB TASHLANG
4. Muhimlik (importance) bo'yicha SORT qiling — eng muhimlar birinchi
5. SHAXSIY fikr, bashorat, yozmang — FAQAT faktlar
6. Har bir item keyin original source link ko'rsating
7. Sentiment emoji qo'shing: 🟢 ijobiy, 🔴 salbiy, ⚪️ neytral

QUYIDAGI YANGILIKLAR (original content + source links):

{items_text}

Quyidagi JSON formatida FAQAT javob qaytaring (markdown yo'q, tushuntirish yo'q):
{{
  "items": [
    {{
      "text": "1–3 qisqa gap, FAQAT o'zbek tilida Lotin alifbosi",
      "sentiment": "bullish/bearish/neutral",
      "source_link": "original URL",
      "importance": 80
    }}
  ]
}}
"""


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

        # Build items text for AI prompt
        items_for_ai = []
        for item in news_items:
            title = getattr(item, "title", "") or ""
            summary = getattr(item, "analysis", "") or getattr(item, "summary", "") or ""
            sentiment = getattr(item, "sentiment", "neutral") or "neutral"
            importance = getattr(item, "importance_score", 50) or 50
            source_url = getattr(item, "source_url", "") or ""

            # Use fetched original content if available, otherwise DB summary
            original = ""
            if source_contents and item.id in source_contents:
                original = source_contents[item.id][:1000]
            elif summary:
                original = summary[:500]

            items_for_ai.append({
                "title": title,
                "content": original,
                "sentiment": sentiment,
                "importance": importance,
                "source_url": source_url,
            })

        items_text = self._format_items_for_prompt(items_for_ai)

        try:
            prompt = DIGEST_GENERATE_PROMPT.format(items_text=items_text)
            ai_response = await self.ai_service.primary.generate(
                prompt,
                system="Siz kunlik kripto yangiliklar digest muallifidir. Barcha javoblar FAQAT o'zbek tilida (Lotin alifbosi) bo'lishi shart. FAQAT JSON formatida javob qaytaring.",
            )
            return self._parse_ai_response(ai_response)

        except Exception as e:
            logger.error("AI digest generation failed: %s", e)
            # Fallback: simple list without AI processing
            return self._fallback_digest(items_for_ai)

    def _format_items_for_prompt(self, items: list[dict]) -> str:
        """Format news items as text for the AI prompt."""
        lines = []
        for i, item in enumerate(items):
            sentiment_str = item.get("sentiment", "neutral")
            importance_str = item.get("importance", 50)
            source = item.get("source_url", "")
            content = item.get("content", "")
            title = item.get("title", "")

            block = f"[{i+1}] "
            if sentiment_str:
                block += f"Sentiment: {sentiment_str}. "
            if importance_str:
                block += f"Importance: {importance_str}. "
            block += f"\nSarlavha: {title}"
            if content:
                block += f"\nOriginal content: {content}"
            if source:
                block += f"\nSource link: {source}"
            lines.append(block)

        return "\n\n".join(lines)

    def _parse_ai_response(self, text: str) -> list[dict]:
        """Parse AI JSON response into digest items."""
        try:
            # Extract JSON from response
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                lines = lines[1:-1]
                text = "\n".join(lines)

            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON found")

            data = json.loads(text[start:end])
            items = data.get("items", [])

            # Validate and normalize each item
            result = []
            for item in items:
                result.append({
                    "text": item.get("text", ""),
                    "sentiment": item.get("sentiment", "neutral"),
                    "source_link": item.get("source_link", ""),
                    "importance": int(item.get("importance", 50)),
                })

            # Sort by importance descending
            result.sort(key=lambda x: x["importance"], reverse=True)
            return result

        except Exception as e:
            logger.error("Failed to parse digest AI response: %s | text: %s", e, text[:300])
            return []

    def _fallback_digest(self, items: list[dict]) -> list[dict]:
        """Simple fallback when AI fails — just deduplicate titles and sort by importance."""
        seen_titles = set()
        result = []
        for item in items:
            title_lower = item.get("title", "").lower()[:50]
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)
            result.append({
                "text": item.get("title", ""),
                "sentiment": item.get("sentiment", "neutral"),
                "source_link": item.get("source_url", ""),
                "importance": item.get("importance", 50),
            })
        result.sort(key=lambda x: x["importance"], reverse=True)
        return result

    async def close(self) -> None:
        """Clean up resources."""
        await self.fetcher.close()
