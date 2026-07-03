"""Settings repository for database operations."""

from typing import Optional, List, Any
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.models.settings import Settings
from app.core.database.repositories.base import BaseRepository


class SettingsRepository(BaseRepository[Settings]):
    """Repository for Settings model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Settings, session)

    async def get_by_key(self, key: str) -> Optional[Settings]:
        """Get setting by key."""
        result = await self.session.execute(
            select(Settings).where(Settings.key == key)
        )
        return result.scalar_one_or_none()

    async def get_value(self, key: str, default: Any = None) -> Any:
        """Get setting value by key with optional default."""
        setting = await self.get_by_key(key)
        if setting:
            if setting.value_type == "int":
                return int(setting.value)
            elif setting.value_type == "float":
                return float(setting.value)
            elif setting.value_type == "bool":
                return setting.value.lower() in ("true", "1", "yes")
            elif setting.value_type == "json":
                return json.loads(setting.value)
            else:
                return setting.value
        return default

    async def set_value(self, key: str, value: Any, value_type: str = "string", description: str = None) -> Settings:
        """Set or update a setting value."""
        existing = await self.get_by_key(key)
        if existing:
            return await self.update(
                existing.id,
                {
                    "value": str(value),
                    "value_type": value_type,
                },
            )
        else:
            return await self.create(
                {
                    "key": key,
                    "value": str(value),
                    "value_type": value_type,
                    "description": description,
                }
            )

    async def get_all_settings(self) -> List[Settings]:
        """Get all settings."""
        return await self.get_all(limit=1000)

    async def get_editable_settings(self) -> List[Settings]:
        """Get all editable settings."""
        result = await self.session.execute(
            select(Settings).where(Settings.is_editable == True)
        )
        return list(result.scalars().all())
