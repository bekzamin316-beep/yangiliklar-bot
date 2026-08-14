"""One-off: re-edit Telegram channel digest announcement posts in Uzbek.

The digest channel post (published by ``publish_digest_message``) only contains
the English/AI titles + summary. After the Telegraph page is retranslated we
re-run the rewrite for those same news items, rebuild the announcement text in
Uzbek, and edit the original channel message in place via editMessageText.

Triggered via env:
  FIX_POSTS=1                    — edit every published digest post from the last 48h
  FIX_POST_MSG_ID=<int>          — edit only that one message id
"""

import asyncio
import logging
import os

from src.core.config import settings
from src.core.database import get_session, init_db, close_db
from src.core.logging_config import setup_logging
from src.core.repositories import NewsRepository
from src.digest.rewriter import DigestRewriter
from src.telegram_bot.publisher import Publisher
from src.telegram_bot.bot import create_bot

logger = logging.getLogger(__name__)


async def fix_posts() -> dict:
    setup_logging()
    await init_db()
    try:
        target_msg = os.environ.get("FIX_POST_MSG_ID", "").strip()
        list_only = os.environ.get("FIX_POSTS_LIST") == "1"
        async with get_session() as session:
            repo = NewsRepository(session)
            from sqlalchemy import select
            from src.models.news import News
            if target_msg:
                result = await session.execute(
                    select(News).where(News.channel_message_id == int(target_msg))
                    .order_by(News.created_at)
                )
            else:
                from datetime import datetime, timedelta, timezone
                since = datetime.now(timezone.utc) - timedelta(hours=24)
                result = await session.execute(
                    select(News).where(
                        News.is_published.is_(True),
                        News.channel_message_id.is_not(None),
                        News.created_at >= since,
                    ).order_by(News.created_at)
                )
            news_items = list(result.scalars().all())

        if not news_items:
            logger.info("No published news with msg_id found")
            return {"edited": 0, "error": None}

        # Group by channel message id
        groups: dict[int, list] = {}
        for n in news_items:
            groups.setdefault(int(n.channel_message_id), []).append(n)

        if list_only:
            logger.info("=== Found %d digest posts (last 24h) ===", len(groups))
            for msg_id, items in sorted(groups.items()):
                logger.info("msg_id=%d items=%d first=%s", msg_id, len(items), items[0].title[:50])
            return {"found": len(groups), "error": None}

        bot = create_bot()
        publisher = Publisher(bot)
        rewriter = DigestRewriter()
        edited = 0

        for msg_id, items in sorted(groups.items()):
            logger.info("Editing post msg_id=%d (%d items)", msg_id, len(items))
            # Build rewrite items (mirrors TelegraphDigestService._rewrite_news)
            rewrite_items = []
            for item in items:
                rewrite_items.append({
                    "title": item.title,
                    "content": (item.summary or item.title),
                    "source_url": item.source_url or "",
                    "source_name": item.source_name or "",
                    "published_at": item.created_at.strftime("%d.%m.%Y %H:%M") if getattr(item, "created_at", None) else "",
                    "importance": item.importance_score,
                    "fallback": {
                        "title_uz": item.title,
                        "summary_uz": item.summary or item.title,
                        "analysis_uz": item.analysis or "",
                        "sentiment": item.sentiment or "neutral",
                        "tags": item.tags or "",
                    },
                })
            rewritten = await rewriter.rewrite_many(rewrite_items)
            if not rewritten:
                logger.warning("Rewrite produced nothing for msg_id=%d — skipping", msg_id)
                continue

            footer = await rewriter.generate_market_summary(rewritten)

            # Rebuild announcement text (same format as publish_digest_message)
            import html
            from src.digest.telegraph_digest import TelegraphDigestService
            svc = TelegraphDigestService.__new__(TelegraphDigestService)
            now = datetime.now(timezone.utc)
            title = svc._announcement_title(now)
            ai_summary = (footer.get("overall_summary") or "").strip()
            telegraph_url = ""
            async with get_session() as session:
                from src.core.repositories import DigestRepository
                repo = DigestRepository(session)
                recent = await repo.get_recent(limit=1)
                if recent:
                    telegraph_url = recent[0].telegraph_url or ""

            lines = [title, "", f"📊 <b>{len(rewritten)} ta yangilik</b>", ""]
            for r in rewritten:
                t = str(r.get("title_uz") or "").strip()
                if t:
                    lines.append(f"<b>{html.escape(t)}</b>")
            lines.append("")
            if ai_summary:
                lines.append(html.escape(ai_summary))
                lines.append("")
            lines.append(f"📖 <a href=\"{telegraph_url}\">To'liq digest — Telegraph'da o'qing</a>")
            text = "\n".join(lines)

            ok = await publisher.edit_message_text(msg_id, text)
            if ok:
                edited += 1
                logger.info("Edited post msg_id=%d", msg_id)
            await asyncio.sleep(2)

        logger.info("Posts fix complete: %d edited", edited)
        return {"edited": edited, "error": None}
    finally:
        await close_db()


if __name__ == "__main__":
    result = asyncio.run(fix_posts())
    print(result)
