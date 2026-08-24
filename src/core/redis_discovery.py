"""Best-effort discovery of the project Redis over Railway's private network.

Railway services in the same project/environment reach each other via
``<service>.railway.internal`` DNS names. When REDIS_URL isn't explicitly
configured we probe the conventional service names, verify with PING, and
hand back a working connection so the bot can use Redis without any panel
variables.
"""

import asyncio
import logging
import socket

from src.core.config import settings

logger = logging.getLogger(__name__)

_CANDIDATE_SERVICES = ("redis", "redis-redis", "cache", "redis-cache")
_redis_port = 6379

_cached: tuple[str, object] | None = None
_done = False


def _configured_url_is_placeholder() -> bool:
    """True when redis_url is unset or still the localhost default."""
    u = (settings.redis_url or "").strip().lower()
    return (not u) or "localhost" in u or "127.0.0.1" in u


def _resolve(host: str) -> str | None:
    try:
        infos = socket.getaddrinfo(host, _redis_port, proto=socket.IPPROTO_TCP)
        return infos[0][4][0]
    except OSError:
        return None


async def discover() -> tuple[str, object] | None:
    """Return (url, connected_client) or None when Redis is unavailable.

    Result is cached for the process lifetime.
    """
    global _cached, _done
    if _done:
        return _cached
    _done = True

    if not _configured_url_is_placeholder():
        url = settings.redis_url.strip()
    else:
        ip = None
        for name in _CANDIDATE_SERVICES:
            host = f"{name}.railway.internal"
            ip = await asyncio.to_thread(_resolve, host)
            if ip:
                logger.info("Redis candidate found: %s → %s", host, ip)
                break
        if not ip:
            logger.info("No project Redis on the private network — using in-memory fallback")
            return None
        url = f"redis://{ip}:{_redis_port}/0"

    client = None
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        await client.ping()
    except Exception as e:
        logger.warning("Redis at %s not usable (%s) — using in-memory fallback", url, str(e)[:120])
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass
        return None

    logger.info("Redis connected via auto-discovery")
    _cached = (url, client)
    return _cached
