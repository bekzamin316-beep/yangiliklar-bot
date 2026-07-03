"""Telegram bot middlewares."""

from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, User
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.repositories.user_repository import UserRepository
import logging

logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """Middleware to provide database session to handlers."""

    def __init__(self, session_factory: AsyncSession):
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Add database session to handler data."""
        async with self.session_factory() as session:
            data["db_session"] = session
            return await handler(event, data)


class AdminLoggingMiddleware(BaseMiddleware):
    """Middleware to log admin actions."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Log admin actions."""
        if isinstance(event, Message):
            user: User = event.from_user
            logger.info(f"Admin action by {user.username} ({user.id}): {event.text}")
        elif isinstance(event, CallbackQuery):
            user: User = event.from_user
            logger.info(f"Admin callback by {user.username} ({user.id}): {event.data}")
        
        return await handler(event, data)
