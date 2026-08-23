"""High-level AI service with retry, model-level fallback, and rotation."""

import logging
import time

from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.ai_service.models import NewsAnalysis
from src.ai_service.rate_limit import ModelDailyLimiter
from src.ai_service.summarizer import DashScopeProvider, OmniRouteProvider, OpenRouterProvider
from src.ai_service.translation import TranslationService

logger = logging.getLogger(__name__)


def _has_cyrillic(text: str) -> bool:
    """Return True when text contains Cyrillic characters (e.g. Russian)."""
    return any("\u0400" <= ch <= "\u04ff" for ch in text)


def _needs_translation(text: str | None) -> bool:
    """Return True if text looks like English or Russian and should be translated.

    The AI prompts already request Uzbek output, but occasionally Latin-script
    English or Cyrillic Russian leaks through. Cyrillic is detected directly;
    English is detected cheaply via common stopwords that do not appear in
    Uzbek text, avoiding unnecessary API calls.
    """
    if not text:
        return False
    if _has_cyrillic(text):
        return True
    lowered = text.lower()
    english_markers = {
        "the", "and", "of", "to", "in", "is", "for", "that", "with", "on",
        "as", "by", "at", "from", "are", "was", "were", "have", "has", "had",
        "will", "would", "could", "should", "this", "these", "those", "an", "a",
        "about", "after", "before", "between", "during", "into", "over", "under",
    }
    return any(marker in lowered.split() for marker in english_markers)


class AIService:
    """AI service with model-level fallback — tries each model before giving up."""

    def __init__(self):
        # Choose provider based on config
        if settings.ai_provider == "openrouter":
            self.primary = OpenRouterProvider()
        elif settings.ai_provider == "omniroute":
            self.primary = OmniRouteProvider()
        else:
            self.primary = DashScopeProvider()

        # Backup provider (if configured) — otherwise auto-fallback to DashScope
        # when its key is set, so a rate-limited primary never blocks the bot.
        if settings.ai_backup_api_key:
            if settings.ai_backup_provider == "openrouter":
                self.backup = OpenRouterProvider()
            elif settings.ai_backup_provider == "omniroute":
                self.backup = OmniRouteProvider()
            else:
                self.backup = DashScopeProvider()
            if settings.ai_model_backup:
                self.backup.model = settings.ai_model_backup
        elif settings.dashscope_api_key and settings.ai_provider != "dashscope":
            self.backup = DashScopeProvider()
            self.backup.model = settings.ai_model_backup or "qwen-plus"
        else:
            self.backup = None

        # Translator — always uses DashScope qwen-turbo for reliability
        self.translator = TranslationService() if settings.enable_translation else None

        # Model rotation + fallback chain
        self._process_count = 0
        self._models = settings.ai_models_list
        self._rotate_every = settings.ai_rotate_every
        # Track models that hit quota limits — skip them for a while
        self._quota_exhausted: dict[str, tuple[int, int]] = {}  # model → (timestamp, cooldown_seconds)

        # Strict per-model daily rate limiting (free OpenRouter models)
        self._limiter = ModelDailyLimiter()
        self._limiter_ready = False

    async def init_rate_limiter(self) -> None:
        """Initialize the Redis-backed daily rate limiter (call on startup)."""
        await self._limiter.init()
        self._limiter_ready = True

    async def close_rate_limiter(self) -> None:
        """Close the rate limiter's Redis connection."""
        await self._limiter.aclose()
        self._limiter_ready = False

    async def _ensure_limiter(self) -> None:
        """Lazily init the limiter once on first use."""
        if not self._limiter_ready:
            await self._limiter.init()
            self._limiter_ready = True

    async def _daily_limit_ok(self, model: str) -> bool:
        """True if model is under its strict daily quota."""
        await self._ensure_limiter()
        if self._limiter.enabled:
            return await self._limiter.can_use(model)
        return True

    async def _record_model_use(self, model: str) -> None:
        """Increment the model's daily usage counter."""
        await self._ensure_limiter()
        if self._limiter.enabled:
            await self._limiter.record_use(model)

    @property
    def models(self) -> list[str]:
        """The configured model rotation chain (public accessor)."""
        return list(self._models)

    def _get_current_model(self) -> str:
        """Return the current model based on rotation state."""
        if self._rotate_every > 0 and len(self._models) > 1:
            idx = (self._process_count // self._rotate_every) % len(self._models)
            return self._models[idx]
        return self._models[0]

    def _get_fallback_models(self, failed_model: str) -> list[str]:
        """Return models to try as fallback, excluding the failed one and unavailable ones."""
        candidates = [m for m in self._models if m != failed_model]
        # Also skip models recently marked unavailable (quota exhausted, rate limited)
        now = int(time.monotonic())
        recent_unavailable = [m for m, (ts, cooldown) in self._quota_exhausted.items() if now - ts < cooldown]
        if recent_unavailable:
            logger.info("Skipping recently unavailable models: %s", recent_unavailable)
            candidates = [m for m in candidates if m not in recent_unavailable]
        return candidates

    def _mark_quota_exhausted(self, model: str, cooldown: int = 1800) -> None:
        """Mark a model as temporarily unavailable so it's skipped for ``cooldown`` seconds."""
        self._quota_exhausted[model] = (int(time.monotonic()), cooldown)
        logger.warning("Model %s marked as unavailable, skipping for %ds", model, cooldown)

    def _advance_rotation(self) -> None:
        """Advance the process counter and rotate model if needed."""
        self._process_count += 1
        if self._rotate_every > 0 and len(self._models) > 1:
            old_idx = ((self._process_count - 1) // self._rotate_every) % len(self._models)
            new_idx = (self._process_count // self._rotate_every) % len(self._models)
            if old_idx != new_idx:
                logger.info("Model rotation: %s → %s (item #%d)",
                            self._models[old_idx], self._models[new_idx], self._process_count)

    async def _try_model(self, model: str, title: str, content: str) -> NewsAnalysis | None:
        """Try a single model for analysis. Returns None if it fails (so we can try next)."""
        if not await self._daily_limit_ok(model):
            return None
        try:
            self.primary.model = model
            analysis = await self.primary.analyze_news(title, content)
            await self._record_model_use(model)

            # Post-process: translate any leaked non-Uzbek text and ensure title is set
            analysis = await self._post_process_analysis(analysis, title)
            return analysis
        except Exception as e:
            err_str = str(e)
            # A 404 "model unavailable for free" means the model slug is wrong /
            # no longer free — do NOT burn daily quota on it.
            if "404" in err_str or "unavailable for free" in err_str.lower():
                logger.warning("Model %s is not available on OpenRouter free tier: %s", model, err_str[:100])
                return None
            # Real API attempts (rate limit / quota / 5xx) consume daily budget
            await self._record_model_use(model)
            # Detect quota exhaustion (403 with "free quota has been exhausted")
            if "403" in err_str and ("quota" in err_str.lower() or "exhausted" in err_str.lower()):
                self._mark_quota_exhausted(model)
            # OmniRoute rate limits (429) — rate limits reset in ~1 minute
            if "429" in err_str or "rate limit" in err_str.lower():
                self._mark_quota_exhausted(model, cooldown=90)
            logger.warning("Model %s failed: %s", model, err_str[:100])
            return None

    async def _post_process_analysis(self, analysis: NewsAnalysis, original_title: str) -> NewsAnalysis:
        """Ensure analysis output is clean: translated to Uzbek and title set."""
        # AI prompt already requires Uzbek output. Only translate if the model
        # leaked Latin-script text, to avoid wasting tokens/API calls.
        if self.translator:
            if analysis.summary_uz and _needs_translation(analysis.summary_uz):
                analysis.summary_uz = await self.translator.translate_to_uzbek(analysis.summary_uz)
            if analysis.analysis_uz and _needs_translation(analysis.analysis_uz):
                analysis.analysis_uz = await self.translator.translate_to_uzbek(analysis.analysis_uz)

        # Fallback title if AI didn't provide one
        if not analysis.title_uz.strip() and original_title:
            if self.translator:
                try:
                    analysis.title_uz = await self.translator.translate_to_uzbek(original_title)
                except Exception as e:
                    logger.warning("Title translation failed: %s", e)
            if not analysis.title_uz.strip():
                analysis.title_uz = original_title

        # Fallback summary if empty
        if not analysis.summary_uz.strip():
            analysis.summary_uz = analysis.title_uz or original_title

        # Fallback analysis if empty
        if not analysis.analysis_uz.strip():
            analysis.analysis_uz = "Yangilik tavsifi mavjud emas."

        # Validate sentiment
        if analysis.sentiment not in {"bullish", "bearish", "neutral"}:
            analysis.sentiment = "neutral"

        return analysis

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    async def analyze_article(self, title: str, content: str) -> NewsAnalysis:
        """Alias for compatibility — same as analyze_news()."""
        return await self.analyze_news(title, content)

    async def analyze_news(self, title: str, content: str) -> NewsAnalysis:
        """Analyze news with model-level fallback chain.

        1. Try current rotation model
        2. If it fails → try each fallback model in rotation list
        3. If all fail → try backup provider
        4. If everything fails → return minimal analysis with translation
        """
        model = self._get_current_model()
        logger.info("Using model: %s (item #%d)", model, self._process_count + 1)

        # Step 1: Try current model
        analysis = await self._try_model(model, title, content)
        if analysis:
            self._advance_rotation()
            return analysis

        # Step 2: Try fallback models one by one
        fallback_models = self._get_fallback_models(model)
        for fallback_model in fallback_models:
            logger.info("Fallback: trying model %s", fallback_model)
            analysis = await self._try_model(fallback_model, title, content)
            if analysis:
                self._advance_rotation()
                return analysis

        # Step 3: Try backup provider (if configured)
        if self.backup:
            try:
                logger.info("Trying backup AI provider...")
                analysis = await self.backup.analyze_news(title, content)
                analysis = await self._post_process_analysis(analysis, title)
                self._advance_rotation()
                return analysis
            except Exception as e2:
                logger.error("Backup AI provider also failed: %s", e2)

        # Step 4: Minimal analysis with translation fallback
        self._advance_rotation()
        logger.warning("All models failed for: %s — returning minimal analysis", title[:50])
        fallback_title = title
        fallback_summary = title
        if self.translator:
            try:
                fallback_title = await self.translator.translate_to_uzbek(title)
                fallback_summary = fallback_title
            except Exception as te:
                logger.error("Fallback translation also failed: %s", te)
        return NewsAnalysis(
            title_uz=fallback_title,
            summary_uz=fallback_summary,
            analysis_uz="Yangilik tavsifi mavjud emas.",
            importance_score=50,
            sentiment="neutral",
        )

    async def create_digest(self, news_items: list[dict]) -> list[dict]:
        """Generate a daily digest with model-level fallback."""
        # Try each model for digest
        model = self._get_current_model()
        fallback_models = self._get_fallback_models(model)

        for try_model in [model] + fallback_models:
            if not await self._daily_limit_ok(try_model):
                logger.info("Skipping %s — daily limit reached", try_model)
                continue
            try:
                self.primary.model = try_model
                digest_items = await self.primary.generate_digest(news_items)
                await self._record_model_use(try_model)

                if self.translator:
                    for item in digest_items:
                        text = item.get("text") or ""
                        if text and _needs_translation(text):
                            item["text"] = await self.translator.translate_to_uzbek(text)

                return digest_items
            except Exception as e:
                err_str = str(e)
                # Don't burn daily quota on models that aren't available as free
                if "404" in err_str or "unavailable for free" in err_str.lower():
                    logger.warning("Digest model %s not available on free tier: %s", try_model, err_str[:100])
                    continue
                await self._record_model_use(try_model)
                if "403" in err_str and ("quota" in err_str.lower() or "exhausted" in err_str.lower()):
                    self._mark_quota_exhausted(try_model)
                if "429" in err_str or "rate limit" in err_str.lower():
                    self._mark_quota_exhausted(try_model, cooldown=90)
                logger.warning("Digest model %s failed: %s", try_model, err_str[:100])

        # Backup provider
        if self.backup:
            try:
                digest_items = await self.backup.generate_digest(news_items)
                if self.translator:
                    for item in digest_items:
                        text = item.get("text") or ""
                        if text and _needs_translation(text):
                            item["text"] = await self.translator.translate_to_uzbek(text)
                return digest_items
            except Exception as e2:
                logger.error("Backup digest also failed: %s", e2)

        return []
