"""Admin filter — only admin users can access admin handlers."""

from aiogram import types
from aiogram.filters import BaseFilter

from src.core.config import settings


class AdminFilter(BaseFilter):
    """Allow only admin users (by telegram_id)."""

    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        if isinstance(event, types.Message):
            user_id = event.from_user.id
        elif isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id
        else:
            return False
        return user_id in settings.admin_id_list
