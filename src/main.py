"""Main entry point — starts the bot, scheduler, and all services."""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging_config import setup_logging
from src.core.database import init_db, close_db
from src.news_collector.collector import NewsCollector
from src.telegram_bot.bot import create_bot, create_dispatcher
from src.telegram_bot.publisher import Publisher
from src.scheduler.scheduler import create_scheduler

logger = logging.getLogger(__name__)


async def on_startup(bot, publisher: Publisher) -> None:
    """Actions to run on bot startup."""
    # Seed RSS sources from .env
    collector = NewsCollector()
    await collector.ensure_sources_seeded()

    # One-off: fix the latest digest page (retranslate into Uzbek)
    import os
    if os.environ.get("FIX_DIGEST") == "1":
        logger.info("FIX_DIGEST=1 detected — running digest fix...")
        try:
            from src.digest.fix_last_digest import fix_last_digest
            result = await fix_last_digest()
            logger.info("Digest fix result: %s", result)
        except Exception as e:
            logger.error("Digest fix failed: %s", e, exc_info=True)

    # One-off: re-edit Telegram channel digest announcement posts in Uzbek
    if os.environ.get("FIX_POSTS") == "1":
        logger.info("FIX_POSTS=1 detected — editing channel digest posts...")
        try:
            from src.digest.fix_posts import fix_posts
            result = await fix_posts()
            logger.info("Posts fix result: %s", result)
        except Exception as e:
            logger.error("Posts fix failed: %s", e, exc_info=True)

    # Load dedup cache from DB
    from src.scheduler.jobs import init_dedup_cache
    await init_dedup_cache()

    # Load custom AI prompt from DB (if admin set one)
    from src.core.database import get_session
    from src.core.repositories import SettingsRepository
    from src.ai_service.prompt_loader import set_analysis_prompt
    async with get_session() as session:
        settings_repo = SettingsRepository(session)
        custom_prompt = await settings_repo.get_value("ai_analysis_prompt")
        if custom_prompt:
            set_analysis_prompt(custom_prompt)
            logger.info("Loaded custom AI prompt from DB")

    # Notify admins
    me = await bot.get_me()
    try:
        from src.digest.schedule import get_schedule_times
        digest_schedule = ", ".join(await get_schedule_times())
    except Exception:
        digest_schedule = ", ".join(settings.digest_schedule_list)
    await publisher.send_admin_notification(
        f"🚀 <b>Bot ishga tushdi!</b>\n\n"
        f"🤖 @{me.username}\n"
        f"📡 AI: {settings.ai_provider} / {settings.ai_model}\n"
        f"🔗 RSS manbalar: {len(settings.rss_source_list)}\n"
        f"⏱ Interval: {settings.news_check_interval}s\n"
        f"📅 Digest jadvallari: {digest_schedule} ({settings.digest_timezone})"
    )
    logger.info("Bot started: @%s", me.username)

    # One-off: trigger a single digest immediately (for on-demand testing)
    import os as _os
    if _os.environ.get("RUN_DIGEST_NOW") == "1":
        logger.info("RUN_DIGEST_NOW=1 detected — triggering one-off digest...")
        try:
            from src.scheduler.jobs import generate_telegraph_digest
            result = await generate_telegraph_digest(publisher)
            logger.info("One-off digest result: %s", result)
            await publisher.send_admin_notification(
                f"📬 <b>Digest yuborildi!</b>\n\n"
                f"📰 Yangiliklar: {result.get('news_count', 0)}\n"
                f"📖 Sahifa: {result.get('telegraph_url', '')}\n"
                f"✅ Status: {'Yuborildi' if result.get('sent') else 'Beklapti'}"
            )
        except Exception as e:
            logger.error("One-off digest failed: %s", e, exc_info=True)
            await publisher.send_admin_notification(f"❌ <b>Digest xato:</b> {e}")


async def on_shutdown(bot, scheduler) -> None:
    """Actions to run on bot shutdown."""
    scheduler.shutdown(wait=False)
    await bot.session.close()
    await close_db()
    logger.info("Bot stopped")


async def main() -> None:
    """Application entry point."""
    setup_logging()
    logger.info("=" * 60)
    logger.info("Crypto News AI Bot — Starting up...")
    logger.info("=" * 60)

    # 1. Initialize database
    await init_db()
    logger.info("Database initialized")

    # 2. Create bot and dispatcher
    bot = create_bot()
    dp = await create_dispatcher()

    # 3. Create publisher
    publisher = Publisher(bot)

    # 4. Create and start scheduler
    scheduler = create_scheduler(publisher)
    scheduler.start()
    logger.info("Scheduler started")

    # 5. Run startup actions
    await on_startup(bot, publisher)

    # 6. Start polling
    logger.info("Starting Telegram polling...")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received")
    finally:
        await on_shutdown(bot, scheduler)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)
