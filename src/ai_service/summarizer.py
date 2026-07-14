"""DashScope (Qwen) AI provider — OpenAI-compatible interface."""

import asyncio
import json
import logging
import time

import httpx

from src.core.config import settings
from src.ai_service.models import NewsAnalysis

logger = logging.getLogger(__name__)


# Default prompts stored as fallback when DB is empty
ANALYZE_NEWS_PROMPT = """Siz kripto yangiliklar tahlilchisidir. Quyidagi yangilikni o'qing va FAQAT JSON formatida natija qaytaring (markdown yo'q, tushuntirish yo'q).

MUHIM: Barcha matn maydonlari FAQAT o'zbek tilida (Lotin alifbosi) yozilishi shart. Rus tilida YO'Q, ingliz tilida YO'Q.

MUHIM QOIDA: analysis_uz maydonida SHAXSIY fikr, bashorat, yoki "bozor ta'siri" haqida YOZMANG. Faqat yangilikning o'ziga oid batafsil tavsif yozing — nima sodir bo'ldi, qanday holat, qaysi detallar muhim.

Sarlavha: {title}
Tarkibi: {content}

Quyidagi strukturada JSON qaytaring:
{{
  "summary_uz": "Yangilik haqida qisqacha xulosa o'zbek tilida (1-2 gap, FAQAT Lotin alifbosi)",
  "analysis_uz": "Yangilik haqida batafsil tavsif o'zbek tilida (3-4 gap, nima sodir bo'ldi, muhim detallar, FAQAT Lotin alifbosi). SHAXSIY fikr YOZMANG!",
  "importance_score": 75,
  "sentiment": "bullish",
  "tags": ["Bitcoin", "ETF"]
}}

Sentiment: bullish, bearish, neutral
Importance score: 0-100 (ne qadar muhim, shuncha yuqori)
ESLATMA: summary_uz va analysis_uz maydonlari FAQAT o'zbek tilida (Lotin alifbosi) bo'lishi shart!
"""

# Runtime override — set via admin panel, persisted in DB
_custom_analysis_prompt: str | None = None


def get_analysis_prompt() -> str:
    """Return the current analysis prompt (custom override or default)."""
    return _custom_analysis_prompt if _custom_analysis_prompt else ANALYZE_NEWS_PROMPT


def set_analysis_prompt(prompt: str) -> None:
    """Set a custom analysis prompt (called from admin panel)."""
    global _custom_analysis_prompt
    _custom_analysis_prompt = prompt

DIGEST_PROMPT = """Siz kripto yangiliklar tahlilchisidir. Quyidagi yangiliklar asosida kunlik digest tayyorlang va FAQAT JSON formatida natija qaytaring (markdown yo'q, tushuntirish yo'q).

MUHIM: Barcha matn maydonlari FAQAT o'zbek tilida (Lotin alifbosi) yozilishi shart. Rus tilida YO'Q, ingliz tilida YO'Q.

Yangiliklar:
{news_items}

Quyidagi strukturada JSON qaytaring:
{{
  "summary": "Bugungi kriptovalyuta bozori bo'yicha qisqacha xulosa o'zbek tilida (3-4 gap, FAQAT Lotin alifbosi)",
  "most_bullish": "Eng ijobiy yangilik o'zbek tilida (1-2 gap, FAQAT Lotin alifbosi)",
  "most_bearish": "Eng salbiy yangilik o'zbek tilida (1-2 gap, FAQAT Lotin alifbosi, agar bo'lmasa null)"
}}
"""


class DashScopeProvider:
    """DashScope Qwen API provider (OpenAI-compatible)."""

    def __init__(self):
        self.api_base = settings.dashscope_api_base
        self.api_key = settings.dashscope_api_key
        self.model = settings.ai_model
        self.timeout = settings.request_timeout

    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Send a prompt and return the AI's text response."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                start = time.monotonic()
                resp = await client.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 2000,
                        **({"enable_thinking": False} if "14b" in self.model and "qwen3" in self.model else {}),
                    },
                )
                elapsed_ms = (time.monotonic() - start) * 1000
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                logger.debug("DashScope response in %.0fms, model=%s", elapsed_ms, self.model)
                return text
        except httpx.TimeoutException as e:
            logger.error("DashScope timeout (%s): type=%s, url=%s", self.timeout, type(e).__name__, self.api_base)
            raise
        except httpx.HTTPStatusError as e:
            # Handle 403 forbidden (expired key) and 429 rate limit
            if e.response.status_code == 429:
                wait_time = 15
                logger.warning("DashScope rate limit hit, waiting %ds before retry...", wait_time)
                await asyncio.sleep(wait_time)
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.post(
                            f"{self.api_base}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": self.model,
                                "messages": messages,
                                "temperature": 0.7,
                                "max_tokens": 2000,
                                **({"enable_thinking": False} if "14b" in self.model and "qwen3" in self.model else {}),
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        text = data["choices"][0]["message"]["content"]
                        return text
                except Exception as retry_e:
                    logger.error("DashScope retry after 429 also failed: %s", retry_e)
                    raise
            logger.error("DashScope HTTP error: %d %s — body: %s", e.response.status_code, e.response.reason_phrase, e.response.text[:300])
            raise
        except Exception as e:
            logger.error("DashScope unexpected error: type=%s, msg=%s", type(e).__name__, e)
            raise

    async def analyze_news(self, title: str, content: str) -> NewsAnalysis:
        """Analyze a single news article and return structured analysis."""
        prompt = get_analysis_prompt().format(
            title=title[:2000],
            content=content[:4000],
        )
        text = await self.generate(prompt, system="Siz kripto yangiliklar tahlilchisidir. Barcha javoblar FAQAT o'zbek tilida (Lotin alifbosi) bo'lishi shart.")
        return self._parse_analysis(text)

    async def generate_digest(self, news_items: list[dict]) -> dict:
        """Generate a daily digest summary from a list of news items."""
        items_text = "\n\n".join(
            f"[{i+1}] {item.get('title', '')} — {item.get('summary', '')[:200]}"
            for i, item in enumerate(news_items[:15])
        )
        prompt = DIGEST_PROMPT.format(news_items=items_text)
        text = await self.generate(prompt, system="Siz kripto yangiliklar digest muallifidir. Barcha javoblar FAQAT o'zbek tilida (Lotin alifbosi) bo'lishi shart.")
        return self._parse_digest(text)

    @staticmethod
    def _parse_analysis(text: str) -> NewsAnalysis:
        """Parse JSON response into NewsAnalysis."""
        try:
            data = DashScopeProvider._extract_json(text)
            return NewsAnalysis(
                summary_uz=data.get("summary_uz", ""),
                analysis_uz=data.get("analysis_uz", ""),
                importance_score=int(data.get("importance_score", 50)),
                sentiment=data.get("sentiment", "neutral"),
                tags=data.get("tags", []),
            )
        except Exception as e:
            logger.error("Failed to parse AI analysis: %s | text: %s", e, text[:200])
            return NewsAnalysis(importance_score=50)

    @staticmethod
    def _parse_digest(text: str) -> dict:
        """Parse JSON response into digest dict."""
        try:
            return DashScopeProvider._extract_json(text)
        except Exception as e:
            logger.error("Failed to parse digest: %s | text: %s", e, text[:200])
            return {
                "summary": "Bugun kriptovalyuta bozorida turli xil yangiliklar bo'ldi.",
                "most_bullish": "",
                "most_bearish": "",
            }

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON from AI response text (handles markdown code blocks)."""
        text = text.strip()
        # Remove markdown code block if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:-1]  # Remove ``` lines
            text = "\n".join(lines)
        # Find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in response")
        return json.loads(text[start:end])


class OpenRouterProvider:
    """OpenRouter AI provider with free models."""

    def __init__(self):
        self.api_base = settings.openrouter_api_base
        self.api_key = settings.openrouter_api_key
        self.model = settings.ai_model
        self.timeout = settings.request_timeout

    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Send a prompt and return the AI's text response."""
        # Respect OpenRouter free-tier rate limits (~20 RPM)
        await asyncio.sleep(2)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                start = time.monotonic()
                resp = await client.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "Referer": "https://github.com/crypto-news-bot",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 2000,
                    },
                )
                elapsed_ms = (time.monotonic() - start) * 1000
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                logger.debug("OpenRouter response in %.0fms, model=%s", elapsed_ms, self.model)
                return text
        except httpx.TimeoutException as e:
            logger.error("OpenRouter timeout (%s): type=%s, url=%s", self.timeout, type(e).__name__, self.api_base)
            raise
        except httpx.HTTPStatusError as e:
            # Handle 429 rate limit with longer wait and retry once
            if e.response.status_code == 429:
                wait_time = 15
                logger.warning("OpenRouter rate limit hit, waiting %ds before retry...", wait_time)
                await asyncio.sleep(wait_time)
                # Retry the request once
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.post(
                            f"{self.api_base}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json",
                                "Referer": "https://github.com/crypto-news-bot",
                            },
                            json={
                                "model": self.model,
                                "messages": messages,
                                "temperature": 0.7,
                                "max_tokens": 2000,
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        text = data["choices"][0]["message"]["content"]
                        return text
                except Exception as retry_e:
                    logger.error("OpenRouter retry after 429 also failed: %s", retry_e)
                    raise
            logger.error("OpenRouter HTTP error: %d %s — body: %s", e.response.status_code, e.response.reason_phrase, e.response.text[:300])
            raise
        except Exception as e:
            logger.error("OpenRouter unexpected error: type=%s, msg=%s", type(e).__name__, e)
            raise

    async def analyze_news(self, title: str, content: str) -> NewsAnalysis:
        """Analyze a single news article and return structured analysis."""
        prompt = get_analysis_prompt().format(
            title=title[:2000],
            content=content[:4000],
        )
        text = await self.generate(prompt, system="Siz kripto yangiliklar tahlilchisidir. Barcha javoblar FAQAT o'zbek tilida (Lotin alifbosi) bo'lishi shart.")
        return DashScopeProvider._parse_analysis(text)

    async def generate_digest(self, news_items: list[dict]) -> dict:
        """Generate a daily digest summary from a list of news items."""
        items_text = "\n\n".join(
            f"[{i+1}] {item.get('title', '')} — {item.get('summary', '')[:200]}"
            for i, item in enumerate(news_items[:15])
        )
        prompt = DIGEST_PROMPT.format(news_items=items_text)
        text = await self.generate(prompt, system="Siz kripto yangiliklar digest muallifidir. Barcha javoblar FAQAT o'zbek tilida (Lotin alifbosi) bo'lishi shart.")
        return DashScopeProvider._parse_digest(text)
