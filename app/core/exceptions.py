"""Custom exceptions for the application."""


class AppException(Exception):
    """Base exception for the application."""

    def __init__(self, message: str = None):
        self.message = message or self.__doc__
        super().__init__(self.message)


class DatabaseException(AppException):
    """Database related exceptions."""
    pass


class AIProviderException(AppException):
    """AI provider related exceptions."""
    pass


class RSSException(AppException):
    """RSS fetching related exceptions."""
    pass


class TelegramException(AppException):
    """Telegram bot related exceptions."""
    pass


class DuplicateNewsException(AppException):
    """Duplicate news detected exception."""
    pass


class ConfigurationException(AppException):
    """Configuration related exceptions."""
    pass
