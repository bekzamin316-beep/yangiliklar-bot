"""Main entry point for the Crypto News AI Bot."""

import asyncio
import logging
import sys
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.telegram.bot import create_bot, create_dispatcher, create_database_engine, create_session_factory, create_redis_client
from app.telegram.middlewares import DatabaseMiddleware
from aiogram import Bot
from app.ai.services.fallback_service import FallbackAIService
from app.scheduler.jobs import NewsScheduler
import redis.asyncio as redis

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


async def main():
    """Main application entry point."""
    logger.info("Starting Crypto News AI Bot...")
    
    # Initialize components
    bot = create_bot()
    redis_client = await create_redis_client()
    engine = create_database_engine()
    session_factory = create_session_factory(engine)
    dp = create_dispatcher(bot, redis_client)
    
    # Setup middlewares
    db_middleware = DatabaseMiddleware(session_factory)
    dp.message.middleware(db_middleware)
    dp.callback_query.middleware(db_middleware)
    
    # Initialize AI service with fallback
    ai_service = FallbackAIService()
    
    # Initialize scheduler
    scheduler = AsyncIOScheduler()
    news_scheduler = NewsScheduler(
        db_session_factory=session_factory,
        bot=bot,
        ai_service=ai_service
    )
    
    # Schedule news collection job
    scheduler.add_job(
        news_scheduler.collect_and_publish_news,
        trigger=IntervalTrigger(seconds=settings.NEWS_CHECK_INTERVAL),
        id='news_collection',
        name='Collect and publish news',
        replace_existing=True
    )
    
    # Schedule daily digest job
    digest_hour, digest_minute = map(int, settings.DIGEST_TIME.split(':'))
    scheduler.add_job(
        news_scheduler.generate_daily_digest,
        trigger=CronTrigger(hour=digest_hour, minute=digest_minute, timezone=settings.DIGEST_TIMEZONE),
        id='daily_digest',
        name='Generate daily digest',
        replace_existing=True
    )
    
    # Start scheduler
    scheduler.start()
    logger.info(f"Scheduler started. News check interval: {settings.NEWS_CHECK_INTERVAL}s, Digest time: {settings.DIGEST_TIME}")
    
    # Startup notification
    try:
        await bot.send_message(
            settings.ADMIN_ID,
            "🤖 **Bot ishga tushdi!**\n\n"
            "✅ Barcha xizmatlar ishlayapti.\n"
            f"📰 Yangiliklar har {settings.NEWS_CHECK_INTERVAL // 60} daqiqada tekshiriladi.\n"
            f"📊 Daily Digest: {settings.DIGEST_TIME} ({settings.DIGEST_TIMEZONE})\n\n"
            "/admin - Admin panelni ochish",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")
    
    # Start polling
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        # Cleanup
        scheduler.shutdown()
        await bot.session.close()
        await engine.dispose()
        await redis_client.close()
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
