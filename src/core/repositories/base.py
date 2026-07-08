"""Generic base repository with common CRUD operations."""

from typing import Generic, List, Optional, Sequence, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """Generic CRUD repository for any ORM model."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, obj_id: int) -> Optional[ModelType]:
        """Get a single entity by its primary key."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == obj_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelType]:
        """Get all entities with pagination."""
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def count(self) -> int:
        """Count all entities."""
        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar_one()

    async def create(self, **kwargs) -> ModelType:
        """Create a new entity."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        try:
            await self.session.commit()
            await self.session.refresh(instance)
        except IntegrityError:
            await self.session.rollback()
            raise
        return instance

    async def update(self, obj_id: int, **kwargs) -> Optional[ModelType]:
        """Update an entity by ID."""
        instance = await self.get_by_id(obj_id)
        if instance is None:
            return None
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def delete(self, obj_id: int) -> bool:
        """Delete an entity by ID."""
        instance = await self.get_by_id(obj_id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.commit()
        return True
