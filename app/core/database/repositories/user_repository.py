"""User repository for database operations."""

from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.models.user import User, Admin
from app.core.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Get user by Telegram ID."""
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self, telegram_id: int, username: str = None, first_name: str = None, last_name: str = None
    ) -> User:
        """Create new user or update existing one."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            await self.update(
                user.id,
                {
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                },
            )
            return await self.get_by_telegram_id(telegram_id)
        else:
            return await self.create(
                {
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                }
            )

    async def is_admin(self, telegram_id: int) -> bool:
        """Check if user is admin."""
        user = await self.get_by_telegram_id(telegram_id)
        return user is not None and user.is_admin


class AdminRepository(BaseRepository[Admin]):
    """Repository for Admin model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Admin, session)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Admin]:
        """Get admin by Telegram ID."""
        result = await self.session.execute(
            select(Admin).where(Admin.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def is_admin(self, telegram_id: int) -> bool:
        """Check if Telegram ID belongs to an admin."""
        admin = await self.get_by_telegram_id(telegram_id)
        return admin is not None and admin.is_active

    async def get_all_admins(self) -> List[Admin]:
        """Get all active admins."""
        result = await self.session.execute(
            select(Admin).where(Admin.is_active == True)
        )
        return list(result.scalars().all())
