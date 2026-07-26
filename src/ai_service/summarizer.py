"""AI providers — DashScope and OpenRouter with shared parsing logic."""

import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx

from src.core.config import settings
from src.ai_service.models import NewsAnalysis
from src.ai_service.prompt_loader import get_analysis_prompt, load_prompt

logger = logging.getLogger(__name__)

# Valid sentiment values
_VALID_SENTIMENTS = {"bullish", "bearish", "neutral"}


class BaseAIProvider:
    """Shared logic for AI providers (prompt building, JSON parsing, HTTP)."""

    def __init__(self) -> None:
        self.model = settings.ai_model
        self.timeout = settings.request_timeout

    # ------------------------------------------------------------------
    # Provider-specific overrides
    # ------------------------------------------------------------------
    @property
    def api_base(self) -> str:
        raise NotImplementedError  # pragma: no cover

    @property
    def api_key(self) -> str:
        raise NotImplementedError  # pragma: no cover

    def _extra_headers(self) -> dict[str, str]:
        return {}

    def _extra_payload(self) -> dict[str, Any]:
        return {}

    async def _before_request(self) -> None:
        """Optional hook called before every API request."""
        pass  # pragma: no cover

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------
    async def analyze_news(self, title: str, content: str) -> NewsAnalysis:
        """Analyze a single news article and return structured analysis."""
        prompt = get_analysis_prompt().format(
            title=title[:2000],
            content=content[:4000],
        )
        system = load_prompt("system_analyze")
        text = await self.generate(prompt, system=system)
        try:
            return self._parse_analysis(text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("JSON parse failed for analysis, retrying once: %s", e)
            retry_prompt = prompt + "\n\nESLATMA: Oldingi javob noto'g'ri JSON edi. FAQAT to'g'ri JSON qaytaring, markdown va izoh yo'q."
            text = await self.generate(retry_prompt, system=system)
            return self._parse_analysis(text)

    async def generate_digest(self, news_items: list[dict]) -> list[dict]:
        """Generate a daily digest summary from a list of news items."""
        items_text = "\n\n".join(
            f"[{i+1}] {item.get('title', '')} - {item.get('content', '')[:200]}"
            for i, item in enumerate(news_items[:15])
        )
        prompt = load_prompt("digest").format(news_items=items_text)
        system = load_prompt("system_digest")
        text = await self.generate(prompt, system=system)
        try:
            return self._parse_digest(text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("JSON parse failed for digest, retrying once: %s", e)
            retry_prompt = prompt + "\n\nESLATMA: Oldingi javob noto'g'ri JSON edi. FAQAT to'g'ri JSON qaytaring, markdown va izoh yo'q."
            text = await self.generate(retry_prompt, system=system)
            return self._parse_digest(text)

    # ------------------------------------------------------------------
    # Shared HTTP layer
    # ------------------------------------------------------------------
    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Send a prompt to the provider and return the AI's text response."""
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
            **self._extra_payload(),
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self._extra_headers(),
        }

        url = f"{self.api_base}/chat/completions"
        await self._before_request()
        return await self._post_chat_completions(url, headers, payload)

    async def _post_chat_completions(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> str:
        """Execute one chat/completions request with 429 retry."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                start = time.monotonic()
                resp = await client.post(url, headers=headers, json=payload)
                elapsed_ms = (time.monotonic() - start) * 1000
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                logger.debug("AI response in %.0fms, model=%s", elapsed_ms, self.model)
                return text
        except httpx.TimeoutException as e:
            logger.error("AI timeout (%s): type=%s, url=%s", self.timeout, type(e).__name__, url)
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("AI rate limit hit, waiting 15s before retry...")
                await asyncio.sleep(15)
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.post(url, headers=headers, json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        return data["choices"][0]["message"]["content"]
                except Exception as retry_e:
                    logger.error("AI retry after 429 also failed: %s", retry_e)
                    raise
            logger.error("AI HTTP error: %d %s - body: %s", e.response.status_code, e.response.reason_phrase, e.response.text[:300])
            raise
        except Exception as e:
            logger.error("AI unexpected error: type=%s, msg=%s", type(e).__name__, e)
            raise

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_analysis(text: str) -> NewsAnalysis:
        """Parse JSON response into NewsAnalysis with strict validation."""
        data = BaseAIProvider._extract_json(text)
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")

        sentiment = str(data.get("sentiment", "neutral")).lower().strip()
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"

        importance = data.get("importance_score", 50)
        try:
            importance = int(importance)
        except (TypeError, ValueError):
            importance = 50
        importance = max(0, min(100, importance))

        tags = data.get("tags", []) or []
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip() for t in tags if t]

        title_uz = str(data.get("title_uz", "") or "").strip()
        summary_uz = str(data.get("summary_uz", "") or "").strip()
        analysis_uz = str(data.get("analysis_uz", "") or "").strip()

        return NewsAnalysis(
            title_uz=title_uz,
            summary_uz=summary_uz,
            analysis_uz=analysis_uz,
            importance_score=importance,
            sentiment=sentiment,
            tags=tags,
        )

    @staticmethod
    def _parse_digest(text: str) -> list[dict]:
        """Parse JSON response into a list of digest items."""
        data = BaseAIProvider._extract_json(text)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", [])
        else:
            raise ValueError(f"Expected JSON object or array, got {type(data).__name__}")

        if not isinstance(items, list):
            raise ValueError("'items' must be a list")
        return BaseAIProvider._normalize_digest_items(items)

    @staticmethod
    def _normalize_digest_items(items: list) -> list[dict]:
        """Validate and normalize digest items."""
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "") or "").strip()
            if not text:
                continue
            sentiment = str(item.get("sentiment", "neutral") or "neutral").lower().strip()
            if sentiment not in {"bullish", "bearish", "neutral"}:
                sentiment = "neutral"
            try:
                importance = int(item.get("importance", 50) or 50)
            except (TypeError, ValueError):
                importance = 50
            result.append({
                "text": text,
                "sentiment": sentiment,
                "source_link": str(item.get("source_link", "") or "").strip(),
                "importance": max(0, min(100, importance)),
            })
        return result

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Extract and parse JSON from AI response text.

        Handles markdown code blocks, extra text, and common formatting issues.
        """
        text = text.strip()

        # Remove markdown code block markers
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3].strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Find balanced JSON object or array
        for start_char, end_char in (("{", "}"), ("[", "]")):
            start_idx = text.find(start_char)
            if start_idx == -1:
                continue
            depth = 0
            for i, ch in enumerate(text[start_idx:], start=start_idx):
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        candidate = text[start_idx : i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            cleaned = BaseAIProvider._clean_json(candidate)
                            try:
                                return json.loads(cleaned)
                            except json.JSONDecodeError as e:
                                raise ValueError(f"Failed to parse extracted JSON: {e}")
            # Unbalanced
            continue

        raise ValueError("No JSON object or array found in response")

    @staticmethod
    def _clean_json(text: str) -> str:
        """Clean common JSON formatting issues."""
        # Replace curly/smart quotes
        for bad, good in [
            ("\u201c", '"'),
            ("\u201d", '"'),
            ("\u2018", '"'),
            ("\u2019", '"'),
            ("\u2013", "-"),
            ("\u2014", "-"),
            ("\u00a0", " "),
        ]:
            text = text.replace(bad, good)

        # Remove trailing commas before closing braces/brackets
        text = re.sub(r",(\s*[}\]])", r"\1", text)

        # Remove C-style line comments
        text = re.sub(r"//[^\n]*", "", text)

        return text


class DashScopeProvider(BaseAIProvider):
    """DashScope Qwen API provider (OpenAI-compatible)."""

    def __init__(self) -> None:
        super().__init__()
        self._api_base = settings.dashscope_api_base
        self._api_key = settings.dashscope_api_key

    @property
    def api_base(self) -> str:
        return self._api_base

    @property
    def api_key(self) -> str:
        return self._api_key

    def _extra_payload(self) -> dict[str, Any]:
        # Disable thinking for specific Qwen3 models to save tokens
        if "qwen3" in self.model and "14b" in self.model:
            return {"enable_thinking": False}
        return {}


class OpenRouterProvider(BaseAIProvider):
    """OpenRouter AI provider with free models."""

    def __init__(self) -> None:
        super().__init__()
        self._api_base = settings.openrouter_api_base
        self._api_key = settings.openrouter_api_key

    @property
    def api_base(self) -> str:
        return self._api_base

    @property
    def api_key(self) -> str:
        return self._api_key

    def _extra_headers(self) -> dict[str, str]:
        return {"Referer": "https://github.com/crypto-news-bot"}

    async def _before_request(self) -> None:
        # Respect OpenRouter free-tier rate limits (~20 RPM)
        await asyncio.sleep(2)
