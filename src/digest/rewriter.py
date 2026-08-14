"""AI rewriter for digest pages.

Rewrites each collected news item into a detailed Uzbek article (no copy)
with title, summary, commentary, analysis, key facts, sentiment, category —
and generates a market summary + overall AI summary for the end of the page.
"""

import asyncio
import json
import logging
from typing import Any

from src.ai_service.prompt_loader import load_prompt
from src.ai_service.service import AIService

logger = logging.getLogger(__name__)

_VALID_SENTIMENTS = {"bullish", "bearish", "neutral"}

_SENTIMENT_EMOJI = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪️"}


class DigestRewriter:
    """Rewrites news items into detailed Uzbek digest articles via AI."""

    def __init__(self, ai_service: AIService | None = None) -> None:
        self.ai_service = ai_service or AIService()
        # Detailed rewrites produce long outputs that can outlive the default
        # request timeout. This instance owns its provider, so we can safely
        # raise the limit without affecting the collection/analysis jobs.
        try:
            self.ai_service.primary.timeout = max(self.ai_service.primary.timeout, 180)
            if self.ai_service.backup is not None:
                self.ai_service.backup.timeout = max(self.ai_service.backup.timeout, 180)
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────

    async def rewrite_many(self, items: list[dict], concurrency: int = 1) -> list[dict]:
        """Rewrite a batch of news items.

        Runs with bounded concurrency (default 1 — the OmniRoute queue rejects
        parallel requests to the same model). Each input item is a dict with
        keys: title, content, source_url, source_name, published_at, fallback
        (existing analysis dict). Items that fail AI rewriting keep their
        fallback fields so the digest never silently drops a news item.
        """
        if not items:
            return []

        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _one(item: dict) -> dict:
            async with semaphore:
                return await self.rewrite_news(item)

        results = await asyncio.gather(*[_one(i) for i in items], return_exceptions=True)

        rewritten: list[dict] = []
        for item, result in zip(items, results):
            if isinstance(result, Exception):
                logger.error("Rewrite failed for %s: %s", item.get("title", "")[:50], result)
                rewritten.append(self._fallback_item(item))
            else:
                rewritten.append(result)
        return rewritten

    async def rewrite_news(self, item: dict) -> dict:
        """Rewrite a single news item into the full digest structure.

        Tries the full model rotation chain (primary models, then the backup
        provider), retrying transient errors (503/429/timeouts/502 empty
        upstream) before falling back to the existing analysis fields.
        """
        title = str(item.get("title", "") or "")
        content = str(item.get("content", "") or "")
        prompt = load_prompt("digest_rewrite").format(title=title[:2000], content=content[:4000])
        system = load_prompt("system_analyze")

        text = await self._generate_with_fallback(prompt, system=system, max_tokens=2200)
        if text is None:
            logger.warning("AI rewrite failed for %s — using fallback", title[:50])
            return self._fallback_item(item)
        try:
            data = self._extract_json(text)
            return self._normalize_item(data, item)
        except Exception as e:
            logger.warning("Rewrite JSON parse failed for %s: %s — using fallback", title[:50], e)
            return self._fallback_item(item)

    async def generate_market_summary(self, rewritten_items: list[dict]) -> dict:
        """Generate the market summary + overall AI summary for the page footer."""
        if not rewritten_items:
            return {"market_summary": "", "overall_summary": "", "outlook_uz": ""}

        compact = "\n".join(
            f"- {i.get('title_uz', '')[:150]} | {i.get('sentiment', 'neutral')} | "
            f"{i.get('importance', 50)} | {i.get('summary_uz', '')[:120]}"
            for i in rewritten_items
        )

        try:
            prompt = load_prompt("digest_market_summary").format(items=compact)
            system = load_prompt("system_digest")
            text = await self._generate_with_fallback(prompt, system=system, max_tokens=1400)
            if text is None:
                raise ValueError("All models failed")
            data = self._extract_json(text)
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object")
            return {
                "market_summary": str(data.get("market_summary", "") or "").strip(),
                "overall_summary": str(data.get("overall_summary", "") or "").strip(),
                "outlook_uz": str(data.get("outlook_uz", "") or "").strip(),
            }
        except Exception as e:
            logger.error("Market summary generation failed: %s", e)
            return {"market_summary": "", "overall_summary": "", "outlook_uz": ""}

    # ── Generation with fallback ─────────────────────────────

    async def _generate_with_fallback(self, prompt: str, system: str | None, max_tokens: int) -> str | None:
        """Generate text trying each model in the rotation chain, then backup.

        Returns the raw AI text, or None if every model/provider failed.
        """
        models = list(self.ai_service.models)
        providers = [self.ai_service.primary]
        if self.ai_service.backup is not None:
            providers.append(self.ai_service.backup)

        for provider in providers:
            for model in models:
                try:
                    provider.model = model
                    return await provider.generate(prompt, system=system, max_tokens=max_tokens, json_mode=True)
                except Exception as e:
                    err = str(e)
                    logger.warning("Rewriter model %s (%s) failed: %s",
                                   model, type(provider).__name__, err[:120])
                    # Sleep briefly on transient failures (queue saturation,
                    # rate limits, upstream hiccups); 403/404/etc. just move on
                    # to the next model immediately.
                    if any(marker in err for marker in ("503", "429", "ReadTimeout", "Timeout", "timed out", "502")):
                        await asyncio.sleep(5)
        return None

    # ── Normalization ─────────────────────────────────────────

    def _normalize_item(self, data: Any, item: dict) -> dict:
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")

        sentiment = str(data.get("sentiment", "neutral") or "neutral").lower().strip()
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"

        key_facts = data.get("key_facts", []) or []
        if not isinstance(key_facts, list):
            key_facts = []
        key_facts = [str(f).strip() for f in key_facts if str(f).strip()][:5]

        title_uz = str(data.get("title_uz", "") or "").strip()
        summary_uz = str(data.get("summary_uz", "") or "").strip()
        commentary_uz = str(data.get("commentary_uz", "") or "").strip()
        analysis_uz = str(data.get("analysis_uz", "") or "").strip()
        teaser_uz = str(data.get("teaser_uz", "") or "").strip()
        emoji = str(data.get("emoji", "") or "").strip()
        category = str(data.get("category", "") or "").strip()

        # Fallbacks per field so the page never has empty sections
        if not title_uz:
            title_uz = str(item.get("title", "") or "")
        if not summary_uz:
            summary_uz = title_uz
        if not commentary_uz:
            commentary_uz = analysis_uz or title_uz
        if not analysis_uz:
            analysis_uz = commentary_uz or title_uz
        if not teaser_uz:
            teaser_uz = summary_uz or title_uz
        if not emoji:
            emoji = _SENTIMENT_EMOJI.get(sentiment, "🔹")
        if not category:
            category = "Kripto"
        if not key_facts:
            key_facts = [summary_uz[:160]]

        return {
            "title_uz": title_uz,
            "summary_uz": summary_uz,
            "commentary_uz": commentary_uz,
            "analysis_uz": analysis_uz,
            "teaser_uz": teaser_uz,
            "emoji": emoji,
            "key_facts": key_facts,
            "sentiment": sentiment,
            "category": category,
            "source_url": str(item.get("source_url", "") or "").strip(),
            "source_name": str(item.get("source_name", "") or "").strip(),
            "published_at": item.get("published_at", ""),
            "importance": int(item.get("importance", 50) or 50),
        }

    def _fallback_item(self, item: dict) -> dict:
        """Build an item from existing analysis when AI rewrite fails."""
        fallback = item.get("fallback") or {}
        if isinstance(fallback, dict):
            title_uz = str(fallback.get("title_uz", "") or "") or str(item.get("title", "") or "")
            summary_uz = str(fallback.get("summary_uz", "") or "") or title_uz
            analysis_uz = str(fallback.get("analysis_uz", "") or "") or summary_uz
            sentiment = str(fallback.get("sentiment", "neutral") or "neutral")
            if sentiment not in _VALID_SENTIMENTS:
                sentiment = "neutral"
        else:
            title_uz = str(item.get("title", "") or "")
            summary_uz = title_uz
            analysis_uz = title_uz
            sentiment = "neutral"

        # Derive a category from the first AI tag if available
        category = "Kripto"
        tags = fallback.get("tags", "") if isinstance(fallback, dict) else ""
        if tags:
            first_tag = str(tags).split(",")[0].strip()
            if first_tag:
                category = first_tag[:40]

        return {
            "title_uz": title_uz,
            "summary_uz": summary_uz,
            "commentary_uz": analysis_uz,
            "analysis_uz": analysis_uz,
            "teaser_uz": summary_uz or title_uz,
            "emoji": _SENTIMENT_EMOJI.get(sentiment, "🔹"),
            "key_facts": [summary_uz[:160]],
            "sentiment": sentiment,
            "category": category,
            "source_url": str(item.get("source_url", "") or "").strip(),
            "source_name": str(item.get("source_name", "") or "").strip(),
            "published_at": item.get("published_at", ""),
            "importance": int(item.get("importance", 50) or 50),
        }

    # ── Parsing (reuse shared logic from the AI provider) ─────

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Extract and parse JSON from an AI response."""
        from src.ai_service.summarizer import BaseAIProvider
        return BaseAIProvider._extract_json(text)


async def _parse_json_safely(text: str) -> Any:
    """Parse JSON with a fallback to the shared extractor."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        from src.ai_service.summarizer import BaseAIProvider
        return BaseAIProvider._extract_json(text)
