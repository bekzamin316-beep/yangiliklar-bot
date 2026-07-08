"""Settings repository with typed getters."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repositories.base import BaseRepository
from src.models.settings import Setting


class SettingsRepository(BaseRepository[Setting]):
    """Repository for key/value settings."""

    def __init__(self, session: AsyncSession):
        super().__init__(Setting, session)

    async def get_value(self, key: str) -> Optional[str]:
        """Get a setting value by key."""
        result = await self.session.execute(
            select(Setting).where(Setting.key == key)
        )
        s = result.scalar_one_or_none()
        return s.value if s else None

    async def set_value(
        self, key: str, value: str, value_type: str = "string",
        description: str | None = None,
    ) -> Setting:
        """Set or update a setting."""
        existing = await self._get_by_key(key)
        if existing:
            existing.value = value
            existing.value_type = value_type
            if description:
                existing.description = description
            await self.session.commit()
            return existing
        return await self.create(
            key=key, value=value, value_type=value_type, description=description,
        )

    async def get_int(self, key: str, default: int = 0) -> int:
        """Get a setting value as integer."""
        val = await self.get_value(key)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            return default

    async def get_float(self, key: str, default: float = 0.0) -> float:
        """Get a setting value as float."""
        val = await self.get_value(key)
        if val is None:
            return default
        try:
            return float(val)
        except ValueError:
            return default

    async def delete_key(self, key: str) -> bool:
        """Delete a setting by key."""
        s = await self._get_by_key(key)
        if s is None:
            return False
        await self.session.delete(s)
        await self.session.commit()
        return True

    async def _get_by_key(self, key: str) -> Optional[Setting]:
        result = await self.session.execute(
            select(Setting).where(Setting.key == key)
        )
        return result.scalar_one_or_none()
