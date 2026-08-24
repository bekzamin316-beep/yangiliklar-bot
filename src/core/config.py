"""Application configuration — loaded from .env via pydantic-settings."""

from functools import cached_property
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All application settings from environment variables."""

    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram Bot token")
    telegram_channel_id: str = Field(..., description="Target channel ID")
    telegram_channel_username: str = Field("", description="Target channel username (without @)")
    admin_ids: str = Field("6194170580,240229643", description="Comma-separated admin IDs")
    admin_password: str = Field("", description="Password for admin panel access")

    # Database
    db_type: str = Field("sqlite", description="postgres or sqlite")
    database_url: str = Field(
        "sqlite+aiosqlite:///./cnbot.db",
        description="Async SQLAlchemy URL",
    )

    # Redis
    redis_url: str = Field("redis://localhost:6379/0", description="Redis URL")

    # AI
    ai_provider: str = Field("dashscope", description="Primary AI provider name")
    ai_model: str = Field("qwen-plus", description="AI model name (default, used when no rotation)")
    ai_models: str = Field(
        "qwen3.5-122b-a10b,qwen3.7-plus,qwen3-vl-235b-a22b-thinking,qwen3-vl-32b-thinking,"
        "qwen-plus-2025-07-28,qwen3-max,qwen3.5-plus-2026-02-15,qwen-max,"
        "qwen3-vl-30b-a3b-thinking,qwen3-235b-a22b-thinking-2507,qwen3.7-max-2026-06-08,"
        "qwen3.7-max-preview,qwen3.6-max-preview,qwen3-32b,deepseek-v4-pro-0813,"
        "qwen3.5-397b-a17b,qwen3-vl-plus-2025-09-23,qwen-vl-plus,qwen3.8-27b,"
        "qwen3.7-flash-2026-07-15,qwen3-vl-32b-instruct,qwen3.5-35b-a3b,"
        "qwen3-30b-a3b-thinking-2507,qwen3-coder-plus-2025-09-23,qwen-plus-latest,"
        "qwen3-max-2026-01-23,qwen3-vl-8b-thinking,qwen3-coder-plus,qwen-plus-2025-09-11,"
        "qwen3-vl-flash-2026-01-22,deepseek-v4-flash-0731,qwen3-max-preview,"
        "qwen3-vl-flash-2025-10-15,qwen3.5-flash-2026-02-23,qwen-vl-max,"
        "qwen3.7-max-2026-05-20,qwen3-vl-30b-a3b-instruct,qwen3.7-plus-2026-05-26,"
        "qwen3.8-2.4t-a95b,qwen3-coder-30b-a3b-instruct,qwen3-vl-235b-a22b-instruct,"
        "qwen3-8b,qwen3.6-27b,qwen3-235b-a22b,kimi-k3,qwen3.6-flash-2026-04-16,"
        "qwen3-coder-flash,qwen3-vl-plus,qwen3-next-80b-a3b-thinking,qwen3.5-27b,"
        "qwen3.7-max-2026-05-17,qwen3-30b-a3b,qwen3-vl-flash,qwen3-14b,"
        "qwen3-vl-8b-instruct,qwen3-max-2025-09-23,qwen3-vl-plus-2025-12-19,"
        "qwen-plus-2025-04-28,qwen3-30b-a3b-instruct-2507,qwen3.5-plus,qwen-flash,"
        "qwen3.7-flash,qwen-flash-2025-07-28,qwen3.6-35b-a3b,qwen-plus-2025-07-14,"
        "qwen3-235b-a22b-instruct-2507,qwq-plus,qwen3.6-plus-2026-04-02,"
        "qwen3-coder-plus-2025-07-22,qwen3.5-plus-2026-04-20,qwen3.8-max,qwen3.6-plus,"
        "qwen3.6-flash,qwen3.5-flash,deepseek-v4-pro,deepseek-v4-flash,qwen3-coder-next,"
        "kimi-k2.7-code,glm-5.2,glm-5.1,qwen3-next-80b-a3b-instruct,"
        "qwen3-coder-480b-a35b-instruct,qwen-plus,qwen-turbo,"
        "qwen3-coder-flash-2025-07-28,deepseek-v3.2",
        description="Comma-separated models for rotation (e.g. qwen3.5-122b-a10b,qwen-plus,qwen-turbo)",
    )
    ai_rotate_every: int = Field(5, description="Rotate AI model every N processed items (0 = no rotation)")
    ai_model_daily_limit: int = Field(50, description="Strict daily request limit per AI model (0 = unlimited)")
    ai_daily_limit_enabled: bool = Field(True, description="Enforce strict per-model daily request limits via Redis")
    dashscope_api_key: str = Field("", description="DashScope API key")
    dashscope_api_base: str = Field(
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        description="DashScope API base URL (international endpoint)",
    )

    # OpenRouter
    openrouter_api_key: str = Field("", description="OpenRouter API key")
    openrouter_api_base: str = Field(
        "https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )
    openrouter_free_models: str = Field(
        "openrouter/auto,nvidia/nemotron-3-nano-30b-a3b:free",
        description="Comma-separated list of free models",
    )

    # OmniRoute (self-hosted OpenAI-compatible LLM router on Railway)
    omniroute_api_base: str = Field(
        "https://omniroute-production-8602.up.railway.app/v1",
        description="OmniRoute API base URL (OpenAI-compatible)",
    )
    omniroute_api_key: str = Field("", description="OmniRoute API key (empty = no auth needed)")

    ai_backup_provider: str = Field("", description="Backup AI provider name")
    ai_backup_api_key: str = Field("", description="Backup AI API key")
    ai_model_backup: str = Field("qwen-plus", description="Model used by the backup provider (e.g. omniroute model)")
    fix_digest_url: str = Field("", description="Explicit telegra.ph URL for the FIX_DIGEST one-off retranslate")

    # Translation
    enable_translation: bool = Field(True, description="Enable translation to target language")
    target_language: str = Field("uz", description="Target language code (uz, ru, en)")

    # RSS
    rss_sources: str = Field(
        "https://www.coindesk.com/arc/outboundfeeds/rss/,https://cointelegraph.com/rss",
        description="Comma-separated RSS feed URLs",
    )

    # External APIs
    coingecko_api_key: str = Field("", description="CoinGecko API key")
    cryptopanic_api_key: str = Field("", description="CryptoPanic API key")

    # Scheduler
    news_check_interval: int = Field(300, description="Seconds between news checks")
    live_price_interval: int = Field(60, description="Seconds between live price updates (default 60)")
    digest_hour: int = Field(0, description="Hour for daily digest (legacy single-time setting)")
    digest_minute: int = Field(0, description="Minute for daily digest (legacy single-time setting)")
    digest_timezone: str = Field("Asia/Tashkent", description="Timezone for digest")
    digest_schedule_times: str = Field(
        "08:00,12:00,18:00,22:00",
        description="Comma-separated digest send times in HH:MM (24h), e.g. 08:00,12:00,18:00,22:00",
    )

    # Telegraph (digest pages)
    telegraph_api_base: str = Field("https://api.telegra.ph", description="Telegraph API base URL")
    telegraph_short_name: str = Field("CryptoNews", description="Telegraph account short name")
    telegraph_author_name: str = Field("cripto7yangilik", description="Telegraph page author name")
    telegraph_author_url: str = Field("https://t.me/cripto7yangilik", description="Telegraph page author URL (optional)")
    digest_max_items: int = Field(12, description="Max news items included in one Telegraph digest page")

    # Telegram Client (Telethon) — for reading channel posts in digest
    telegram_api_id: int = Field(0, description="Telegram API ID from my.telegram.org")
    telegram_api_hash: str = Field("", description="Telegram API hash from my.telegram.org")
    telegram_session_name: str = Field("digest_session", description="Telethon session file name")
    telegram_session_string: str = Field("", description="Telethon StringSession for Railway deployment (no file needed)")
    digest_source_channels: str = Field("", description="Comma-separated Telegram channel usernames/IDs to read for digest")

    # Digest cover images
    digest_image_enabled: bool = Field(True, description="Enable auto-generating cover images for digest announcements")
    digest_image_models: str = Field(
        "qwen-image,wan2.2-t2i-plus,wan2.2-t2i-flash",
        description="Comma-separated DashScope image models for fallback chain",
    )
    digest_image_size: str = Field("1024*1024", description="Image size (e.g. 1024*1024)")

    @cached_property
    def digest_image_model_list(self) -> List[str]:
        """Parse comma-separated image models into a list."""
        return [m.strip() for m in self.digest_image_models.split(",") if m.strip()]

    # General
    log_level: str = Field("INFO", description="Logging level")
    request_timeout: int = Field(30, description="HTTP request timeout in seconds")
    importance_threshold: int = Field(50, description="Minimum importance score to publish")
    max_news_per_run: int = Field(20, description="Max news items per collection run")

    @cached_property
    def digest_schedule_list(self) -> List[str]:
        """Parse digest schedule times into a sorted list of 'HH:MM' strings."""
        times = [t.strip() for t in self.digest_schedule_times.split(",") if t.strip()]
        valid = [t for t in times if len(t.split(":")) == 2 and t.split(":")[0].isdigit() and t.split(":")[1].isdigit()]
        if not valid:
            return ["08:00", "12:00", "18:00", "22:00"]
        return sorted(valid)

    @cached_property
    def admin_id_list(self) -> List[int]:
        """Parse comma-separated admin IDs into a list of integers."""
        return [int(sid.strip()) for sid in self.admin_ids.split(",") if sid.strip()]

    @cached_property
    def rss_source_list(self) -> List[str]:
        """Parse comma-separated RSS URLs into a list."""
        return [url.strip() for url in self.rss_sources.split(",") if url.strip()]

    @cached_property
    def ai_models_list(self) -> List[str]:
        """Parse comma-separated AI models for rotation."""
        models = [m.strip() for m in self.ai_models.split(",") if m.strip()]
        return models if models else [self.ai_model]

    @property
    def is_postgres(self) -> bool:
        return self.db_type == "postgres"

    @property
    def is_sqlite(self) -> bool:
        return self.db_type == "sqlite"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton instance
settings = Settings()
