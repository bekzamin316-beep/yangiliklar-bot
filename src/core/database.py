"""Async database session factory using SQLAlchemy 2.0."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.models.base import Base

# Engine — create once, reuse everywhere
_engine_kwargs = {
    "echo": settings.log_level == "DEBUG",
}
if settings.is_postgres:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(settings.database_url, **_engine_kwargs)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session and close it after use."""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables if they don't exist and run migrations for missing columns."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.is_postgres:
            migrations = [
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS source_url TEXT",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS source_name VARCHAR(200)",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS image_url TEXT",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS importance_score INTEGER DEFAULT 0 NOT NULL",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS sentiment VARCHAR(20)",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS tags TEXT",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT FALSE NOT NULL",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS channel_message_id BIGINT",
                "ALTER TABLE news ALTER COLUMN tags TYPE text USING tags::text",
                "ALTER TABLE news DROP COLUMN IF EXISTS hash",
            ]
            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                except Exception:
                    pass


async def close_db() -> None:
    """Dispose of the engine connection pool."""
    await engine.dispose()
