"""User repository."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repositories.base import BaseRepository
from src.models.user import User


class UserRepository(BaseRepository[User]):
    """Repository for the User model."""

    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Find user by Telegram ID."""
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self, telegram_id: int, username: str | None = None,
        first_name: str | None = None, last_name: str | None = None,
    ) -> User:
        """Get existing user or create a new one."""
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = await self.create(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
        else:
            # Update names if they changed
            if username and username != user.username:
                user.username = username
            if first_name and first_name != user.first_name:
                user.first_name = first_name
            if last_name is not None and last_name != user.last_name:
                user.last_name = last_name
            await self.session.commit()
        return user

    async def get_active_count(self) -> int:
        """Count active users."""
        result = await self.session.execute(
            select(User).where(User.is_active == True)  # noqa: E712
        )
        return len(result.scalars().all())
