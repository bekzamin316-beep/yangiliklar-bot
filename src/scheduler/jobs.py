"""Scheduler jobs — news collection and daily digest."""

import asyncio
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

# Serializes all AI-heavy work (collection analysis + digest rewriting) so the
# 24/7 collection job and a running digest never hit the AI provider queue
# concurrently (OmniRoute drops requests that wait too long in its queue).
ai_lock = asyncio.Lock()


async def init_dedup_cache() -> None:
    """Load dedup cache from DB on startup."""
    await _dedup_cache.load_from_db()


async def collect_and_publish_news(publisher: Publisher) -> None:
    """Scheduler job: collect news → analyze → publish each immediately.

    DEPRECATED (kept for backward compatibility): news is now delivered only
    through the 4x/day digest. Prefer :func:`collect_news`.
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


async def collect_news(_lock_held: bool = False) -> int:
    """Scheduler job: collect news → analyze → save to DB (no publishing).

    News is collected 24/7 and stored so the next digest can pick it up.
    Nothing is sent to the channel here — the channel only receives the
    4x/day digest announcements.

    Args:
        _lock_held: internal — True when the caller (the digest service) has
            already acquired :data:`ai_lock`; prevents a self-deadlock.

    Returns the number of newly processed items.
    """
    async def _run() -> int:
        logger.info("=== Starting news collection cycle (digest mode) ===")
        processed_count = 0
        try:
            # 1. Collect raw news from all sources
            collector = NewsCollector()
            raw_items = await collector.collect_all()

            if not raw_items:
                logger.info("No new items collected")
                return 0

            # 2. Process each item: dedup → AI analysis → save to DB
            ai_service = AIService()
            processor = NewsProcessor(ai_service)

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

                    # Save to DB (unpublished — picked up by the next digest)
                    news = await processor._save_news(item, analysis)
                    _dedup_cache.add(item.content_hash(), item.url_hash())
                    processed_count += 1
                    logger.info(
                        "Processed: %s | score=%d | %s",
                        item.title[:50], analysis.importance_score, analysis.sentiment,
                    )

                except Exception as e:
                    logger.error("Error processing %s: %s", item.title[:50], e)

            logger.info("=== Collection cycle complete: %d processed (saved, not published) ===", processed_count)
            return processed_count

        except Exception as e:
            logger.error("Error in collect_news: %s", e, exc_info=True)
            return 0

    if _lock_held:
        return await _run()
    async with ai_lock:
        return await _run()


async def generate_telegraph_digest(publisher: Publisher, dry_run: bool = False) -> dict:
    """Scheduler job: run the full Telegraph digest cycle.

    Collects everything since the last digest, rewrites it in Uzbek via AI,
    publishes one Telegraph page, sends the short announcement to the channel,
    and updates bookkeeping (last digest time, published flags).
    """
    logger.info("=== Starting Telegraph digest cycle ===")
    from src.digest.telegraph_digest import TelegraphDigestService
    service = TelegraphDigestService(publisher)
    return await service.generate(dry_run=dry_run)


async def generate_daily_digest(publisher: Publisher) -> None:
    """Scheduler job: generate and publish daily digest.

    Reads original source content (Telegram posts + web articles),
    uses AI to deduplicate, merge, sort by importance, and format
    as concise 1–3 sentence items with source links.
    """
    logger.info("=== Starting daily digest generation ===")

    try:
        today = date.today()

        # 1. Get today's news from DB
        async with get_session() as session:
            news_repo = NewsRepository(session)
            today_news = await news_repo.get_recent(hours=24, limit=30)

        if not today_news:
            logger.info("No news today, skipping digest")
            return

        # 2. Fetch original content from source URLs (web articles + Telegram posts)
        from src.digest.content_fetcher import ContentFetcher
        fetcher = ContentFetcher()
        source_contents = await fetcher.fetch_all_sources(today_news)

        # Also read configured Telegram channel sources
        channel_posts = await fetcher.fetch_channel_sources(hours=24)

        # 3. Generate digest via AI
        from src.digest.digest_generator import DigestGenerator
        generator = DigestGenerator()
        digest_items = await generator.generate(today_news, source_contents)

        # 4. Format digest message
        digest_text = _format_digest(today, digest_items)

        # 5. Publish to channel
        await publisher.publish_digest(digest_text)

        # 6. Save to DB
        ai_summary = " ".join(item["text"] for item in digest_items[:3])
        most_bullish = next((item["text"] for item in digest_items if item.get("sentiment") == "bullish"), "")
        most_bearish = next((item["text"] for item in digest_items if item.get("sentiment") == "bearish"), "")

        async with get_session() as session:
            digest_repo = DigestRepository(session)
            existing = await digest_repo.get_by_date(today)
            if existing:
                await digest_repo.update(
                    existing.id,
                    ai_summary=ai_summary,
                    full_text=digest_text,
                    most_bullish=most_bullish,
                    most_bearish=most_bearish,
                    is_published=True,
                )
            else:
                await digest_repo.create(
                    digest_date=today,
                    news_count=len(today_news),
                    ai_summary=ai_summary,
                    full_text=digest_text,
                    most_bullish=most_bullish,
                    most_bearish=most_bearish,
                    is_published=True,
                )

        # 7. Clean up
        await fetcher.close()
        await generator.close()

        logger.info("=== Daily digest complete: %d news → %d digest items ===", len(today_news), len(digest_items))

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


def _format_digest(today: date, digest_items: list[dict]) -> str:
    """Format AI-generated digest items as a Telegram HTML message.

    Each item is 1–3 sentences with a sentiment emoji and source link.
    """
    lines = [
        "📰 <b>Kunlik kripto yangiliklar digesti</b>",
        f"📅 {today.strftime('%d.%m.%Y')}",
        f"📊 {len(digest_items)} ta asosiy yangilik",
        "",
    ]

    separator = "—" * 30

    for item in digest_items:
        text = item.get("text", "")
        sentiment = item.get("sentiment", "neutral")
        source_link = item.get("source_link", "")
        emoji = _sentiment_emoji(sentiment)

        if source_link:
            line = f"{emoji} {text}\n🔗 <a href=\"{source_link}\">Batafsil</a>"
        else:
            line = f"{emoji} {text}"

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
