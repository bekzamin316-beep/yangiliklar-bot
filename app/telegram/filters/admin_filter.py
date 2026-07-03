"""Telegram bot filters."""

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from app.core.config import settings


class AdminFilter(BaseFilter):
    """Filter to check if user is admin."""

    async def __call__(self, obj: Message | CallbackQuery) -> bool:
        """Check if user is admin."""
        user_id = None
        
        if isinstance(obj, Message):
            user_id = obj.from_user.id
        elif isinstance(obj, CallbackQuery):
            user_id = obj.from_user.id
        
        if user_id is None:
            return False
        
        return user_id == settings.ADMIN_ID
