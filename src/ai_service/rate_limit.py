"""Strict per-model daily request limit backed by Redis.

Free OpenRouter models come with small daily quotas (e.g. 50 req/day).
This module enforces that limit hard: when a model has consumed its daily
budget it is skipped for the rest of the day, no matter what the API says.

Usage::

    limiter = ModelDailyLimiter()
    await limiter.init()

    if await limiter.can_use("openai/gpt-oss-120b:free"):
        ...
        await limiter.record_use("openai/gpt-oss-120b:free")
"""

import logging
from datetime import datetime, timezone

from src.core.config import settings

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None


class ModelDailyLimiter:
    """Tracks per-model request counts for the current UTC day in Redis."""

    KEY_PREFIX = "ai:daily"

    def __init__(self, daily_limit: int | None = None, enabled: bool | None = None) -> None:
        self.daily_limit = (
            daily_limit
            if daily_limit is not None
            else settings.ai_model_daily_limit
        )
        self.enabled = (
            enabled if enabled is not None else settings.ai_daily_limit_enabled
        )
        self._redis = None

    async def init(self) -> None:
        """Lazily open the Redis connection (only if enabled and redis is available)."""
        if not self.enabled or self.daily_limit <= 0:
            self.enabled = False
            return
        if aioredis is None:
            logger.warning("redis package not installed — daily rate limit disabled")
            self.enabled = False
            return
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            await self._redis.ping()
            logger.info("ModelDailyLimiter connected to Redis (limit=%d req/day)", self.daily_limit)
        except Exception as e:
            logger.warning("Redis unavailable (%s) — daily rate limit disabled", e)
            self.enabled = False
            self._redis = None

    def _key(self, model: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"{self.KEY_PREFIX}:{day}:{model}"

    async def _ttl_until_midnight(self) -> int:
        now = datetime.now(timezone.utc)
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta
        next_midnight = tomorrow + timedelta(days=1)
        return max(1, int((next_midnight - now).total_seconds()))

    async def get_count(self, model: str) -> int:
        """Return how many requests the model already used today."""
        if not self.enabled or self._redis is None:
            return 0
        try:
            val = await self._redis.get(self._key(model))
            return int(val or 0)
        except Exception as e:
            logger.warning("Failed to read daily count for %s: %s", model, e)
            return 0

    async def can_use(self, model: str) -> bool:
        """True if the model still has daily quota left."""
        if not self.enabled or self._redis is None:
            return True
        count = await self.get_count(model)
        if count >= self.daily_limit:
            logger.warning(
                "Model %s hit daily limit (%d/%d) — skipping until UTC midnight",
                model, count, self.daily_limit,
            )
            return False
        return True

    async def record_use(self, model: str) -> None:
        """Increment the model's daily usage counter."""
        if not self.enabled or self._redis is None:
            return
        try:
            key = self._key(model)
            ttl = await self._ttl_until_midnight()
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl)
            await pipe.execute()
        except Exception as e:
            logger.warning("Failed to record daily usage for %s: %s", model, e)

    async def aclose(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
