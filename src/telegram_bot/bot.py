"""Bot setup — creates bot, dispatcher, registers handlers and middleware."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.core.config import settings
from src.telegram_bot.handlers.user_handlers import user_router
from src.telegram_bot.handlers.admin_handlers import admin_router
from src.telegram_bot.middleware.database_middleware import DatabaseMiddleware

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    """Create and return the Bot instance."""
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def create_dispatcher(redis_client=None) -> Dispatcher:
    """Create Dispatcher with all handlers and middleware registered."""

    # Use Redis for FSM storage if available, otherwise memory
    if redis_client:
        storage = RedisStorage(redis=redis_client)
    else:
        from aiogram.fsm.storage.memory import MemoryStorage
        storage = MemoryStorage()
        logger.warning("Redis not available, using in-memory FSM storage")

    dp = Dispatcher(storage=storage)

    # Register middleware on both message and callback_query
    dp.message.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())

    # Register routers — user first, admin second
    dp.include_router(user_router)
    dp.include_router(admin_router)

    logger.info("Dispatcher configured with %d routers", 2)
    return dp
