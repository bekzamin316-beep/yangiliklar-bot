"""Telegram bot initialization and configuration."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.telegram.handlers import admin_router
from app.telegram.middlewares import DatabaseMiddleware
import logging
import redis.asyncio as redis

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    """Create Telegram bot instance."""
    return Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )


def create_dispatcher(bot: Bot, redis_client: redis.Redis) -> Dispatcher:
    """Create dispatcher with all routers and middlewares."""
    dp = Dispatcher(storage=RedisStorage(redis=redis_client))
    
    # Register routers
    dp.include_router(admin_router)
    
    return dp


def create_database_engine():
    """Create SQLAlchemy async engine."""
    return create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )


def create_session_factory(engine):
    """Create async session factory."""
    return async_sessionmaker(
        bind=engine,
        class_=None,  # Will use AsyncSession from sqlalchemy.ext.asyncio
        expire_on_commit=False,
        autoflush=False,
        autocommit=False
    )


async def create_redis_client() -> redis.Redis:
    """Create Redis client."""
    return await redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True
    )


async def on_startup(dp: Dispatcher, bot: Bot):
    """Execute on bot startup."""
    logger.info("Bot starting up...")
    await bot.send_message(
        settings.ADMIN_ID,
        "🤖 Bot ishga tushdi!\n\n"
        "✅ Barcha xizmatlar ishlayapti.\n"
        "/admin - Admin panelni ochish"
    )


async def on_shutdown(dp: Dispatcher, bot: Bot):
    """Execute on bot shutdown."""
    logger.info("Bot shutting down...")
    await bot.send_message(
        settings.ADMIN_ID,
        "⚠️ Bot to'xtatildi."
    )


async def start_bot():
    """Main function to start the bot."""
    from sqlalchemy.ext.asyncio import AsyncSession
    
    # Create components
    bot = create_bot()
    redis_client = await create_redis_client()
    engine = create_database_engine()
    session_factory = create_session_factory(engine)
    dp = create_dispatcher(bot, redis_client)
    
    # Setup middlewares
    db_middleware = DatabaseMiddleware(session_factory)
    dp.message.middleware(db_middleware)
    dp.callback_query.middleware(db_middleware)
    
    # Register startup/shutdown handlers
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Start polling
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()
        await redis_client.close()
