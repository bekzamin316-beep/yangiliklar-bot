"""Base repository with common CRUD operations."""

from typing import TypeVar, Generic, List, Optional, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app.core.database.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository implementing common CRUD operations."""

    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: int) -> Optional[ModelType]:
        """Get a single record by ID."""
        result = await self.session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[ModelType]:
        """Get all records with pagination."""
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, data: Dict[str, Any]) -> ModelType:
        """Create a new record."""
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, id: int, data: Dict[str, Any]) -> Optional[ModelType]:
        """Update an existing record."""
        stmt = update(self.model).where(self.model.id == id).values(**data).returning(self.model)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none()

    async def delete(self, id: int) -> bool:
        """Delete a record by ID."""
        stmt = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def count(self) -> int:
        """Count total records."""
        from sqlalchemy import func
        result = await self.session.execute(select(func.count()).select_from(self.model))
        return result.scalar() or 0
