"""Scheduler jobs — news collection and daily digest."""

import logging
from datetime import date, datetime, timezone

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import NewsRepository, DigestRepository
from src.ai_service.service import AIService
from src.news_collector.collector import NewsCollector
from src.news_collector.dedup_cache import DedupCache
from src.news_collector.processor import NewsProcessor
from src.telegram_bot.publisher import Publisher
from src.crypto_prices.live import LivePriceService

logger = logging.getLogger(__name__)

_dedup_cache = DedupCache()


async def init_dedup_cache() -> None:
    """Load dedup cache from DB on startup."""
    await _dedup_cache.load_from_db()


async def collect_and_publish_news(publisher: Publisher) -> None:
    """Scheduler job: collect news → analyze → publish each immediately.

    Each news item is analyzed and published right away,
    so the channel sees news as soon as it's processed — not after
    waiting for the entire batch to finish.
    """
    logger.info("=== Starting news collection cycle ===")

    try:
        # 1. Collect raw news from all sources
        collector = NewsCollector()
        raw_items = await collector.collect_all()

        if not raw_items:
            logger.info("No new items collected")
            return

        # 2. Process each item and publish immediately
        ai_service = AIService()
        processor = NewsProcessor(ai_service)
        published_count = 0

        for item in raw_items:
            try:
                # Check duplicate via cache
                is_dup = await _dedup_cache.check_or_add(
                    item.content_hash(), item.url_hash()
                )
                if is_dup:
                    logger.debug("Skipping duplicate: %s", item.title[:50])
                    continue

                # AI analysis
                analysis = await ai_service.analyze_news(item.title, item.content)

                # Filter by importance
                if analysis.importance_score < settings.importance_threshold:
                    logger.debug(
                        "Low importance (%d), skipping: %s",
                        analysis.importance_score, item.title[:50],
                    )
                    continue

                # Save to DB
                news = await processor._save_news(item, analysis)
                _dedup_cache.add(item.content_hash(), item.url_hash())
                logger.info(
                    "Processed: %s | score=%d | %s",
                    item.title[:50], analysis.importance_score, analysis.sentiment,
                )

                # Publish immediately to channel
                if await publisher.publish_news(news):
                    published_count += 1

            except Exception as e:
                logger.error("Error processing %s: %s", item.title[:50], e)

        logger.info("=== Collection cycle complete: %d published ===", published_count)

    except Exception as e:
        logger.error("Error in collect_and_publish_news: %s", e, exc_info=True)


async def generate_daily_digest(publisher: Publisher) -> None:
    """Scheduler job: generate and publish daily digest.

    Runs once per day at DIGEST_HOUR:DIGEST_MINUTE.
    """
    logger.info("=== Starting daily digest generation ===")

    try:
        today = date.today()
        ai_service = AIService()

        # 1. Get today's news
        async with get_session() as session:
            news_repo = NewsRepository(session)
            today_news = await news_repo.get_recent(hours=24, limit=20)

        if not today_news:
            logger.info("No news today, skipping digest")
            return

        # 2. Generate digest with AI
        news_dicts = [
            {"title": n.title, "summary": n.summary or ""}
            for n in today_news
        ]
        digest_data = await ai_service.create_digest(news_dicts)

        # 3. Format digest message
        digest_text = _format_digest(today, today_news, digest_data)

        # 4. Publish to channel
        await publisher.publish_digest(digest_text)

        # 5. Save to DB
        async with get_session() as session:
            digest_repo = DigestRepository(session)
            existing = await digest_repo.get_by_date(today)
            if existing:
                await digest_repo.update(existing.id, ai_summary=digest_data.get("summary"))
            else:
                await digest_repo.create(
                    digest_date=today,
                    news_count=len(today_news),
                    ai_summary=digest_data.get("summary"),
                    full_text=digest_text,
                    most_bullish=digest_data.get("most_bullish"),
                    most_bearish=digest_data.get("most_bearish"),
                    is_published=True,
                )

        logger.info("=== Daily digest complete: %d news items ===", len(today_news))

    except Exception as e:
        logger.error("Error in generate_daily_digest: %s", e, exc_info=True)


def _format_digest(today: date, news: list, data: dict) -> str:
    """Format a daily digest as a Telegram HTML message."""
    summary = data.get("summary", "Bugun kriptovalyuta bozorida turli xil yangiliklar bo'ldi.")
    most_bullish = data.get("most_bullish", "")
    most_bearish = data.get("most_bearish", "")

    lines = [
        f"📰 <b>Kundalik Kripto Digest</b>",
        f"📅 {today.strftime('%d.%m.%Y')}",
        f"📊 {len(news)} ta yangilik tahlil qilindi",
        "",
        f"📝 <b>Xulosa:</b>",
        summary,
    ]

    if most_bullish:
        lines.extend(["", f"🟢 <b>Eng ijobiy:</b> {most_bullish}"])
    if most_bearish:
        lines.extend(["", f"🔴 <b>Eng salbiy:</b> {most_bearish}"])

    lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━━"])
    if settings.telegram_channel_username:
        lines.append(f"📢 https://t.me/{settings.telegram_channel_username}")

    return "\n".join(lines)


async def update_live_prices() -> None:
    """Scheduler job: update pinned live crypto prices message."""
    try:
        live_service = LivePriceService()
        await live_service.create_or_update_pinned_message()
    except Exception as e:
        logger.error("Error updating live prices: %s", e)
