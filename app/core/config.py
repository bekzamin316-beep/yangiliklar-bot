"""Application configuration using Pydantic Settings."""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN: str = Field(..., description="Telegram Bot API Token")
    TELEGRAM_CHANNEL_ID: int = Field(..., description="Telegram Channel ID for posting")
    ADMIN_ID: int = Field(..., description="Admin user ID for bot access")

    # Database Configuration
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@db:5432/crypto_news_bot",
        description="PostgreSQL database connection URL"
    )

    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL"
    )

    # AI Provider Configuration
    AI_PROVIDER: str = Field(
        default="openrouter",
        description="Primary AI provider (openrouter, groq, gemini, anthropic, openai, ollama)"
    )
    AI_MODEL: str = Field(
        default="meta-llama/llama-3-70b-instruct",
        description="Default AI model to use"
    )

    # AI API Keys
    OPENROUTER_API_KEY: Optional[str] = Field(default=None, description="OpenRouter API Key")
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq API Key")
    GOOGLE_API_KEY: Optional[str] = Field(default=None, description="Google Gemini API Key")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Anthropic Claude API Key")
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API Key")
    OLLAMA_BASE_URL: str = Field(default="http://ollama:11434", description="Ollama base URL")

    # RSS Sources
    RSS_SOURCES: str = Field(
        default="https://www.coindesk.com/arc/outboundfeeds/rss/,https://cointelegraph.com/rss,https://announcements.binance.com/en/feed,https://blog.bybit.com/feed/,https://medium.com/feed/okx,https://medium.com/feed/kucoin",
        description="Comma-separated list of RSS feed URLs"
    )

    # CryptoPanic API (optional)
    CRYPTOPANIC_API_KEY: Optional[str] = Field(default=None, description="CryptoPanic API Key")

    # CoinGecko API (optional)
    COINGECKO_API_KEY: Optional[str] = Field(default=None, description="CoinGecko API Key")

    # Scheduler Configuration
    DIGEST_TIME: str = Field(default="23:59", description="Daily digest time in HH:MM format")
    DIGEST_TIMEZONE: str = Field(default="UTC", description="Timezone for daily digest")
    NEWS_CHECK_INTERVAL: int = Field(default=300, description="Interval in seconds to check for new news")

    # System Configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    MAX_RETRIES: int = Field(default=3, description="Maximum retry attempts for failed operations")
    REQUEST_TIMEOUT: int = Field(default=30, description="HTTP request timeout in seconds")
    IMPORTANCE_THRESHOLD: int = Field(default=50, description="Minimum importance score to publish news")

    # Security
    ENCRYPTION_KEY: str = Field(..., description="Encryption key for sensitive data")

    @property
    def rss_source_list(self) -> List[str]:
        """Parse RSS sources into a list."""
        return [url.strip() for url in self.RSS_SOURCES.split(",") if url.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()
