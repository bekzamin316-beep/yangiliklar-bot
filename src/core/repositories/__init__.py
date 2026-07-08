"""Repository layer — data access."""

from src.core.repositories.base import BaseRepository
from src.core.repositories.news_repository import NewsRepository
from src.core.repositories.user_repository import UserRepository
from src.core.repositories.settings_repository import SettingsRepository
from src.core.repositories.rss_repository import RSSSourceRepository
from src.core.repositories.digest_repository import DigestRepository, LogRepository

__all__ = [
    "BaseRepository",
    "NewsRepository",
    "UserRepository",
    "SettingsRepository",
    "RSSSourceRepository",
    "DigestRepository",
    "LogRepository",
]
