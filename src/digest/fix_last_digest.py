"""One-off script: retranslate the latest digest page into Uzbek.

Runs inside the deployed container (where the SQLite volume lives). It loads
the most recent published news items, rewrites each through the AI service
(which now uses the OpenRouter + OmniRoute provider chain), and edits the
existing Telegraph page in place so the channel link stays valid.

Intended to be triggered once via ``FIX_DIGEST=1`` env on startup (see main.py),
then removed.
"""

import asyncio
import logging
from datetime import datetime, timezone

from src.core.config import settings
from src.core.database import get_session, init_db, close_db
from src.core.logging_config import setup_logging
from src.core.repositories import NewsRepository, DigestRepository
from src.digest.rewriter import DigestRewriter
from src.digest.telegraph import TelegraphClient
from src.digest.telegraph_digest import TelegraphDigestService

logger = logging.getLogger(__name__)


async def fix_last_digest(dry_run: bool = False) -> dict:
    """Retranslate the most recent digest news and edit the Telegraph page."""
    setup_logging()
    await init_db()

    try:
        # 1. Latest digest record → find its Telegraph path + news
        async with get_session() as session:
            digest_repo = DigestRepository(session)
            recent = await digest_repo.get_recent(limit=1)
            if not recent:
                logger.info("No digest records found — nothing to fix")
                return {"fixed": False, "reason": "no_digest"}

            digest = recent[0]
            telegraph_url = digest.telegraph_url or ""
            msg_id = digest.channel_message_id

            if not telegraph_url:
                logger.info("Latest digest has no Telegraph URL — nothing to fix")
                return {"fixed": False, "reason": "no_telegraph_url"}

            # Load the news that belong to this digest (published with same msg_id)
            news_repo = NewsRepository(session)
            if msg_id:
                try:
                    msg_id_int = int(msg_id)
                except (TypeError, ValueError):
                    msg_id_int = None
                if msg_id_int:
                    from sqlalchemy import select
                    from src.models.news import News
                    result = await session.execute(
                        select(News).where(News.channel_message_id == msg_id_int)
                        .order_by(News.created_at)
                    )
                    news_items = list(result.scalars().all())
                else:
                    news_items = list(await news_repo.get_recent(hours=24, limit=settings.digest_max_items))
            else:
                news_items = list(await news_repo.get_recent(hours=24, limit=settings.digest_max_items))

        if not news_items:
            logger.info("No news items found for the digest — nothing to fix")
            return {"fixed": False, "reason": "no_news"}

        logger.info("Fixing digest: %s (%d news, msg_id=%s)", telegraph_url, len(news_items), msg_id)

        # 2. Rebuild rewrite items (same shape as TelegraphDigestService._rewrite_news)
        from src.digest.content_fetcher import ContentFetcher
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
        finally:
            await fetcher.close()

        # 3. Rewrite via AI (now using OpenRouter + OmniRoute chain)
        rewriter = DigestRewriter()
        rewritten = await rewriter.rewrite_many(rewrite_items)
        if not rewritten:
            logger.warning("All rewrites produced empty results — aborting fix")
            return {"fixed": False, "reason": "empty_rewrite"}

        footer = await rewriter.generate_market_summary(rewritten)

        # 4. Build page HTML and edit the Telegraph page
        svc = TelegraphDigestService.__new__(TelegraphDigestService)
        page_title = svc._page_title(datetime.now(timezone.utc))
        html_content = svc._build_page_html(rewritten, footer)

        path = telegraph_url.rstrip("/").rsplit("/", 1)[-1]
        client = TelegraphClient()
        new_url = await client.edit_page(path, page_title, html_content)

        if not dry_run:
            ai_summary = (footer.get("overall_summary") or "").strip()
            async with get_session() as session:
                digest_repo = DigestRepository(session)
                await digest_repo.update(
                    digest.id,
                    ai_summary=ai_summary,
                    most_bullish=next((i["title_uz"] for i in rewritten if i.get("sentiment") == "bullish"), ""),
                    most_bearish=next((i["title_uz"] for i in rewritten if i.get("sentiment") == "bearish"), ""),
                    telegraph_url=new_url,
                )

        logger.info("Digest page fixed: %s", new_url)
        return {"fixed": True, "url": new_url, "news_count": len(rewritten)}

    finally:
        await close_db()


if __name__ == "__main__":
    result = asyncio.run(fix_last_digest())
    print(result)