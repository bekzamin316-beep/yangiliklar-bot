"""Tiny HTTP health server + self-ping loop for always-on hosting.

Hosting platforms like Hugging Face Spaces put containers to sleep after a
period without inbound HTTP traffic. We expose /health on $PORT (7860) and,
when SPACE_HOST is set, periodically request our own public URL so the
platform never considers the Space idle.
"""

import asyncio
import logging
import os

import httpx
from aiohttp import web

from src.core.config import settings

logger = logging.getLogger(__name__)

PING_INTERVAL_SECONDS = int(os.environ.get("PING_INTERVAL_SECONDS", "600"))  # 10 min < Render's 15-min idle cutoff


async def health_handler(request: web.Request) -> web.Response:
    """Liveness endpoint used by self-pings and external monitors."""
    return web.json_response({
        "status": "ok",
        "bot": f"@{settings.telegram_channel_username}" if settings.telegram_channel_username else "unknown",
        "provider": settings.effective_provider,
        "models": len(settings.effective_model_list),
    })


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    return app


async def start_health_server() -> web.AppRunner:
    """Serve /health on 0.0.0.0:$PORT (default 7860 for HF Spaces)."""
    port = int(os.environ.get("PORT", "7860"))
    runner = web.AppRunner(make_app())
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("Health server listening on 0.0.0.0:%d", port)
    return runner


async def self_ping_loop() -> None:
    """Request our own public URL periodically so the host never idles out."""
    host = os.environ.get("SPACE_HOST", "").strip()
    if not host:
        logger.info("SPACE_HOST not set — self-ping disabled")
        return
    url = f"https://{host}/health"
    logger.info("Self-ping enabled: %s every %ds", url, PING_INTERVAL_SECONDS)
    while True:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                logger.debug("Self-ping %s → %s", url, resp.status_code)
        except Exception as e:
            logger.warning("Self-ping failed (%s) — retrying in %ds", str(e)[:80], PING_INTERVAL_SECONDS)
        await asyncio.sleep(PING_INTERVAL_SECONDS)
