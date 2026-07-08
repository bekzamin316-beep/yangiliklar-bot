"""Database middleware — injects AsyncSession into handler data."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory


class DatabaseMiddleware(BaseMiddleware):
    """Provides an async DB session to every handler via data['session']."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_factory() as session:
            data["session"] = session
            return await handler(event, data)
