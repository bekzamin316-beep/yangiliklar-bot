"""Telegraph digest service.

Orchestrates a full digest cycle:

1. Run a fresh news collection cycle (24/7 collection continues regardless).
2. Load all unpublished news created since the last sent digest.
3. Fetch original source content and rewrite every item into a detailed
   Uzbek article via AI (title, summary, commentary, analysis, key facts,
   sentiment, category).
4. Generate a market summary + overall AI summary for the page footer.
5. Publish everything on ONE Telegraph page.
6. Send only the short announcement to the Telegram channel (title, count,
   AI summary, Telegraph link).
7. Mark included news as published and persist the digest record.
"""

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import DigestRepository, NewsRepository
from src.digest import schedule
from src.digest.content_fetcher import ContentFetcher
from src.digest.rewriter import DigestRewriter
from src.digest.telegraph import TelegraphClient, esc
from src.telegram_bot.publisher import Publisher

logger = logging.getLogger(__name__)

_SENTIMENT_EMOJI = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪️"}


class TelegraphDigestService:
    """Builds and publishes the Telegraph-based digest."""

    def __init__(self, publisher: Publisher) -> None:
        self.publisher = publisher
        self.rewriter = DigestRewriter()
        self.telegraph = TelegraphClient()

    async def generate(self, dry_run: bool = False) -> dict:
        """Run one digest cycle.

        Args:
            dry_run: When True, build everything but do NOT send the channel
                announcement and do NOT mark news as published. Telegraph page
                is still created so the output can be inspected.

        Returns:
            A result dict with keys: news_count, telegraph_url, sent, error.
        """
        try:
            from src.scheduler import jobs as scheduler_jobs

            # All AI-heavy work (collection analysis + rewriting) runs under the
            # shared lock so the 24/7 collection job and this digest never hit
            # the AI provider queue concurrently.
            async with scheduler_jobs.ai_lock:
                # 1. Fresh collection cycle (keeps 24/7 collection going and
                #    ensures the digest window includes the very latest items).
                await scheduler_jobs.collect_news(_lock_held=True)

                # 2. News since last digest
                since, now = await schedule.get_news_since_window()
                news_items = await self._load_news(since)
                if not news_items:
                    logger.info("No new news since %s — digest skipped", since.isoformat())
                    return {"news_count": 0, "telegraph_url": "", "sent": False, "error": None}

                # 3. Fetch original content + rewrite
                rewritten = await self._rewrite_news(news_items)
                if not rewritten:
                    logger.warning("All rewrites produced empty results — digest skipped")
                    return {"news_count": len(news_items), "telegraph_url": "", "sent": False, "error": "empty_rewrite"}

                # 4. Market + overall summary
                footer = await self.rewriter.generate_market_summary(rewritten)

            # 5. Build Telegraph page
            page_title = self._page_title(now)
            html_content = self._build_page_html(rewritten, footer)
            telegraph_url = await self.telegraph.create_page(page_title, html_content)

            if dry_run:
                logger.info("[DRY RUN] Digest ready: %d news, page=%s", len(rewritten), telegraph_url)
                return {"news_count": len(rewritten), "telegraph_url": telegraph_url, "sent": False, "error": None}

            # 6. Channel announcement
            ai_summary = (footer.get("overall_summary") or "").strip()
            announcement_title = self._announcement_title(now)
            msg_id = await self.publisher.publish_digest_message(
                title=announcement_title,
                news_count=len(rewritten),
                ai_summary=ai_summary,
                telegraph_url=telegraph_url,
                news_titles=[item.get("title_uz") for item in rewritten],
            )

            # 7. Persist: mark news published, save digest, update last-sent time
            await self._finalize(news_items, rewritten, msg_id, telegraph_url, footer)
            await schedule.set_last_digest_time(now)

            logger.info(
                "Digest complete: %d news published, page=%s, msg_id=%s",
                len(rewritten), telegraph_url, msg_id,
            )
            return {"news_count": len(rewritten), "telegraph_url": telegraph_url, "sent": msg_id is not None, "error": None}

        except Exception as e:
            logger.error("Telegraph digest failed: %s", e, exc_info=True)
            return {"news_count": 0, "telegraph_url": "", "sent": False, "error": str(e)}

    # ── Steps ─────────────────────────────────────────────────

    async def _load_news(self, since: datetime) -> list:
        """Load unpublished news created since `since`, capped by settings."""
        async with get_session() as session:
            repo = NewsRepository(session)
            items = await repo.get_unpublished_since(since, limit=settings.digest_max_items)
        logger.info("Loaded %d news items since %s", len(items), since.isoformat())
        return list(items)

    async def _rewrite_news(self, news_items: list) -> list[dict]:
        """Fetch original content and rewrite all items via AI."""
        fetcher = ContentFetcher()
        try:
            source_contents = await fetcher.fetch_all_sources(news_items)

            rewrite_items = []
            for item in news_items:
                content = source_contents.get(item.id, "") or (item.summary or item.analysis or "")
                if not content and item.title:
                    content = item.title
                published_at = item.created_at.strftime("%d.%m.%Y %H:%M") if getattr(item, "created_at", None) else ""
                rewrite_items.append({
                    "title": item.title,
                    "content": content,
                    "source_url": item.source_url or "",
                    "source_name": item.source_name or "",
                    "published_at": published_at,
                    "importance": item.importance_score,
                    "fallback": {
                        "title_uz": item.title,
                        "summary_uz": item.summary or item.title,
                        "analysis_uz": item.analysis or "",
                        "sentiment": item.sentiment or "neutral",
                        "tags": item.tags or "",
                    },
                })

            return await self.rewriter.rewrite_many(rewrite_items)
        finally:
            await fetcher.close()

    async def _finalize(
        self,
        news_items: list,
        rewritten: list[dict],
        msg_id: int | None,
        telegraph_url: str,
        footer: dict,
    ) -> None:
        """Mark news as published, save the digest record."""
        published_ids = [getattr(n, "id", None) for n in news_items[: len(rewritten)] if getattr(n, "id", None)]

        async with get_session() as session:
            news_repo = NewsRepository(session)
            for news_id in published_ids:
                await news_repo.update(news_id, is_published=True, channel_message_id=msg_id)

            digest_repo = DigestRepository(session)
            today = date.today()
            existing = await digest_repo.get_by_date(today)
            ai_summary = (footer.get("overall_summary") or "").strip()
            most_bullish = next((i["title_uz"] for i in rewritten if i.get("sentiment") == "bullish"), "")
            most_bearish = next((i["title_uz"] for i in rewritten if i.get("sentiment") == "bearish"), "")

            digest_fields = dict(
                news_count=len(rewritten),
                ai_summary=ai_summary,
                most_bullish=most_bullish,
                most_bearish=most_bearish,
                is_published=True,
                channel_message_id=str(msg_id) if msg_id else None,
                telegraph_url=telegraph_url,
            )

            if existing:
                await digest_repo.update(existing.id, **digest_fields)
            else:
                try:
                    await digest_repo.create(digest_date=today, full_text="", **digest_fields)
                except IntegrityError:
                    # A concurrent digest cycle created the record after our
                    # get_by_date check — update it instead of failing.
                    logger.warning("Digest record for %s already exists (race) — updating", today)
                    existing = await digest_repo.get_by_date(today)
                    if existing:
                        await digest_repo.update(existing.id, **digest_fields)
            logger.info("Marked %d news as published; digest record saved", len(published_ids))

    # ── Formatting ────────────────────────────────────────────

    @staticmethod
    def _localize(now: datetime) -> datetime:
        """Convert a UTC datetime to the configured digest timezone."""
        try:
            return now.astimezone(ZoneInfo(settings.digest_timezone))
        except Exception:
            return now.astimezone()

    @staticmethod
    def _page_title(now: datetime) -> str:
        local = TelegraphDigestService._localize(now)
        return f"Kripto Bozor Digesti — {local.strftime('%d.%m.%Y %H:%M')}"

    @staticmethod
    def _announcement_title(now: datetime) -> str:
        local = TelegraphDigestService._localize(now)
        return f"📰 <b>Kripto Bozor Digesti</b>\n📅 {local.strftime('%d.%m.%Y %H:%M')}"

    def _build_page_html(self, items: list[dict], footer: dict) -> str:
        """Build the full Telegraph page HTML (all news + market/footer summary)."""
        parts: list[str] = []
        parts.append("<p>Quyidagi sahifada oxirgi digestdan beri to'plangan barcha yangiliklar — AI tomonidan o'zbek tilida qayta yozilgan holda keltirilgan.</p>")

        for idx, item in enumerate(items, start=1):
            emoji = _SENTIMENT_EMOJI.get(item.get("sentiment", "neutral"), "⚪️")
            parts.append(f"<h3>{idx}. {esc(item.get('title_uz'))}</h3>")
            parts.append(f"<p><b>📋 Xulosa:</b> {esc(item.get('summary_uz'))}</p>")
            if item.get("commentary_uz"):
                parts.append(f"<p><b>📝 Batafsil sharh:</b> {esc(item.get('commentary_uz'))}</p>")
            if item.get("analysis_uz"):
                parts.append(f"<p><b>🤖 AI tahlili:</b> {esc(item.get('analysis_uz'))}</p>")

            facts = item.get("key_facts") or []
            if facts:
                parts.append("<p><b>📌 Muhim faktlar:</b></p>")
                parts.append("<ul>")
                for f in facts:
                    parts.append(f"<li>{esc(f)}</li>")
                parts.append("</ul>")

            meta = []
            meta.append(f"<b>📊 Bozorga ta'siri:</b> {emoji} {esc(item.get('sentiment', 'neutral').capitalize())}")
            if item.get("category"):
                meta.append(f"<b>🏷 Kategoriya:</b> {esc(item.get('category'))}")
            if item.get("published_at"):
                meta.append(f"<b>🕐 E'lon qilingan:</b> {esc(item.get('published_at'))}")
            parts.append(f"<p>{' • '.join(meta)}</p>")

            source = item.get("source_url") or ""
            if source:
                name = esc(item.get("source_name") or "Manba")
                parts.append(f'<p><b>🔗 Manba:</b> <a href="{esc(source)}">{name}</a></p>')

            parts.append("<p>──────</p>")

        # Footer: market summary + overall AI summary
        market_summary = (footer.get("market_summary") or "").strip()
        overall_summary = (footer.get("overall_summary") or "").strip()

        parts.append("<h2>📊 Bozor xulosasi</h2>")
        parts.append(f"<p>{esc(market_summary) if market_summary else 'Bozor xulosasi mavjud emas.'}</p>")

        parts.append("<h2>🤖 Umumiy AI xulosa</h2>")
        parts.append(f"<p>{esc(overall_summary) if overall_summary else 'Umumiy xulosa mavjud emas.'}</p>")

        parts.append("<p><i>Ushbu digest AI tomonidan avtomatik tayyorlandi va investitsiya tavsiyasi emas.</i></p>")
        return "\n".join(parts)
