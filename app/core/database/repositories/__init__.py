"""Repository module initialization."""

from app.core.database.repositories.base import BaseRepository
from app.core.database.repositories.news_repository import NewsRepository
from app.core.database.repositories.user_repository import UserRepository
from app.core.database.repositories.ai_repository import AIRepository
from app.core.database.repositories.settings_repository import SettingsRepository
from app.core.database.repositories.rss_repository import RSSRepository
from app.core.database.repositories.digest_repository import DigestRepository

__all__ = [
    "BaseRepository",
    "NewsRepository",
    "UserRepository",
    "AIRepository",
    "SettingsRepository",
    "RSSRepository",
    "DigestRepository",
]
