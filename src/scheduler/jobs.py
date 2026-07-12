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

        # 1. Get today's news
        async with get_session() as session:
            news_repo = NewsRepository(session)
            today_news = await news_repo.get_recent(hours=24, limit=20)

        if not today_news:
            logger.info("No news today, skipping digest")
            return

        # 2. Format digest message as a list of news items
        digest_text = _format_digest(today, today_news)

        # 3. Publish to channel
        await publisher.publish_digest(digest_text)

        # 4. Save to DB
        async with get_session() as session:
            digest_repo = DigestRepository(session)
            existing = await digest_repo.get_by_date(today)
            if existing:
                await digest_repo.update(
                    existing.id,
                    ai_summary="",
                    full_text=digest_text,
                    most_bullish="",
                    most_bearish="",
                    is_published=True,
                )
            else:
                await digest_repo.create(
                    digest_date=today,
                    news_count=len(today_news),
                    ai_summary="",
                    full_text=digest_text,
                    most_bullish="",
                    most_bearish="",
                    is_published=True,
                )

        logger.info("=== Daily digest complete: %d news items ===", len(today_news))

    except Exception as e:
        logger.error("Error in generate_daily_digest: %s", e, exc_info=True)


def _sentiment_emoji(sentiment: str | None) -> str:
    """Map a sentiment string to an emoji indicator."""
    if not sentiment:
        return "⚪️"
    s = sentiment.lower()
    if s in ("positive", "bullish", "optimistic", "positive-ish"):
        return "🟢"
    if s in ("negative", "bearish", "pessimistic"):
        return "🔴"
    return "⚪️"


def _format_digest(today: date, news: list) -> str:
    """Format a daily digest as a Telegram HTML list of news items."""
    lines = [
        "📰 <b>Kunlik kripto yangiliklar digesti</b>",
        f"📅 {today.strftime('%d.%m.%Y')}",
        f"📊 {len(news)} ta yangilik",
        "",
    ]

    channel = settings.telegram_channel_username or ""
    separator = "—" * 30

    for item in news:
        emoji = _sentiment_emoji(getattr(item, "sentiment", None))
        title = getattr(item, "title", "") or ""
        message_id = getattr(item, "channel_message_id", None)

        if channel and message_id:
            link = f"https://t.me/{channel}/{message_id}"
            line = f"{emoji} <a href=\"{link}\">{title}</a>"
        elif getattr(item, "source_url", None):
            line = f"{emoji} <a href=\"{item.source_url}\">{title}</a>"
        else:
            line = f"{emoji} {title}"

        lines.append(line)
        lines.append(separator)

    return "\n".join(lines)


# Reuse the same LivePriceService instance across the scheduler and admin handlers
# to avoid duplicate pinned messages when refreshes overlap.
_live_price_service: LivePriceService | None = None


def get_live_price_service() -> LivePriceService:
    """Return the shared LivePriceService singleton."""
    global _live_price_service
    if _live_price_service is None:
        _live_price_service = LivePriceService()
    return _live_price_service


async def update_live_prices() -> None:
    """Scheduler job: update pinned live crypto prices message."""
    try:
        live_service = get_live_price_service()
        await live_service.create_or_update_pinned_message()
    except Exception as e:
        logger.error("Error updating live prices: %s", e)
