"""Image generation service using DashScope async text-to-image API."""

import asyncio
import logging
import time

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class ImageGenerationService:
    """Generate cover images for digest pages via DashScope.

    The DashScope text-to-image API is task-based (async). We submit a task,
    poll until it succeeds, and return the OSS image URL that the result
    contains.  The URL is valid for several days — more than enough for a
    daily digest page that is refreshed every 4 h.
    """

    def __init__(self, models: list[str] | None = None, size: str = "1024*1024"):
        self.models = models or ["qwen-image", "wan2.2-t2i-plus", "wan2.2-t2i-flash"]
        self.size = size
        self.api_base = settings.dashscope_api_base.replace(
            "/compatible-mode/v1", "/api/v1"
        )
        self.api_key = settings.dashscope_api_key
        self.poll_timeout = 180  # seconds to wait for task completion

    # ── Public API ────────────────────────────────────────────────

    async def generate(self, prompt: str) -> str | None:
        """Generate an image from a prompt string.

        Tries each model in the fallback chain until one succeeds.
        Returns the image URL, or ``None`` if every model fails.
        """
        for model in self.models:
            try:
                logger.info("Image gen: trying model %s", model)
                task_id = await self._submit(model, prompt)
                if not task_id:
                    logger.warning("Image gen: no task_id returned for %s", model)
                    continue

                result = await self._poll(task_id)
                if not result:
                    logger.warning("Image gen: task failed or timed out for %s", model)
                    continue

                url = result.get("url")
                if url:
                    logger.info("Image gen: succeeded with %s", model)
                    return url
            except Exception as e:
                logger.warning("Image gen failed with %s: %s", model, e)

        logger.error("All image-gen models failed — skipping image")
        return None

    # ── Internal helpers ──────────────────────────────────────────

    async def _submit(self, model: str, prompt: str) -> str | None:
        """Submit a text-to-image task. Returns task_id on success."""
        body = {
            "model": model,
            "input": {"prompt": prompt},
            "parameters": {"size": self.size, "n": 1},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.api_base}/services/aigc/text2image/image-synthesis",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            output = data.get("output", {})
            return output.get("task_id")

    async def _poll(self, task_id: str) -> dict | None:
        """Poll task status until SUCCEEDED / FAILED / timeout."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        start = time.monotonic()

        while time.monotonic() - start < self.poll_timeout:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.api_base}/tasks/{task_id}", headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                status = data.get("output", {}).get("task_status", "")

                if status == "SUCCEEDED":
                    results = data.get("output", {}).get("results", [])
                    if results:
                        return results[0]
                    return None

                if status == "FAILED":
                    msg = data.get("output", {}).get("message", "unknown error")
                    logger.error("Image task FAILED: %s (id=%s)", msg, task_id)
                    return None

                # PENDING — wait and retry
                await asyncio.sleep(3)

        logger.warning("Image task timed out after %ds (id=%s)", self.poll_timeout, task_id)
        return None
