"""High-level AI service with retry, model-level fallback, and rotation."""

import html
import logging
import time
from collections.abc import Awaitable, Callable

from tenacity import retry, stop_after_attempt, wait_exponential

from src.ai_service.models import NewsAnalysis
from src.ai_service.summarizer import DashScopeProvider, OmniRouteProvider, OpenRouterProvider
from src.ai_service.translation import TranslationService
from src.core.config import settings

logger = logging.getLogger(__name__)

# Module-level admin notifier — registered once at startup (see main.py).
# Every AIService instance picks it up so failures inside jobs, digests, and
# admin handlers all reach the same Telegram admin without extra plumbing.
_admin_notifier: Callable[[str], Awaitable[None]] | None = None


def set_admin_notifier(notifier: Callable[[str], Awaitable[None]] | None) -> None:
    """Register a global async callable used to alert admins about AI issues."""
    global _admin_notifier
    _admin_notifier = notifier


# Cooldowns — failed models are skipped during rotation for these windows.
_FAILED_COOLDOWN_SEC = 600      # any failure: 10 minutes
_QUOTA_COOLDOWN_SEC = 1800      # quota/rate-limit exhausted: 30 minutes
_NOTIFY_THROTTLE_SEC = 900      # max one admin alert per event per 15 minutes


def _needs_translation(text: str | None) -> bool:
    """Return True if text looks like English and should be translated.

    The AI prompts already request Uzbek output, but occasionally Latin-script
    English leaks through. We detect that cheaply by looking for common English
    stopwords that do not appear in Uzbek text, avoiding unnecessary API calls.
    """
    if not text:
        return False
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

        # Backup provider (if configured)
        if settings.ai_backup_api_key:
            if settings.ai_backup_provider == "openrouter":
                self.backup = OpenRouterProvider()
            elif settings.ai_backup_provider == "omniroute":
                self.backup = OmniRouteProvider()
            else:
                self.backup = DashScopeProvider()
            if settings.ai_model_backup:
                self.backup.model = settings.ai_model_backup
        else:
            self.backup = None

        # Translator — always uses DashScope qwen-turbo for reliability
        self.translator = TranslationService() if settings.enable_translation else None

        # Model rotation + fallback chain
        self._process_count = 0
        self._models = settings.ai_models_list
        self._rotate_every = settings.ai_rotate_every
        # Track models that hit quota limits — skip them for a while
        self._quota_exhausted: dict[str, int] = {}  # model_name → timestamp when it failed
        # Track every failing model so broken/unknown models drop out of rotation fast
        self._recently_failed: dict[str, int] = {}  # model_name → monotonic timestamp
        # Throttle admin alerts per event so a 100-item run doesn't spam admins
        self._last_notify_ts: dict[str, float] = {}
        self._notifier: Callable[[str], Awaitable[None]] | None = None
        configured_limit = int(getattr(settings, "ai_max_fallback_attempts", 8) or 0)
        self._max_fallback_attempts = max(1, configured_limit)

    def set_notifier(self, notifier: Callable[[str], Awaitable[None]] | None) -> None:
        """Override the instance-level admin notifier (used when a bot is in hand)."""
        self._notifier = notifier

    @property
    def models(self) -> list[str]:
        """The configured model rotation chain (public accessor)."""
        return list(self._models)

    def get_available_models(self) -> list[str]:
        """Return models that are not currently failed or quota-exhausted.

        Broken or unknown models (bad names, missing on the provider, quota
        drained) fall out of rotation until their cooldown expires, so the bot
        stops wasting requests on models that are known to be dead.
        """
        now = int(time.monotonic())
        unavailable = {
            m for m, ts in self._recently_failed.items() if now - ts < _FAILED_COOLDOWN_SEC
        }
        unavailable |= {
            m for m, ts in self._quota_exhausted.items() if now - ts < _QUOTA_COOLDOWN_SEC
        }
        available = [m for m in self._models if m not in unavailable]
        return available if available else list(self._models)

    async def _notify_admin(self, event: str, text: str, throttle_sec: int = _NOTIFY_THROTTLE_SEC) -> None:
        """Send a throttled admin notification for an AI event."""
        notifier = self._notifier or _admin_notifier
        if notifier is None:
            return
        now = time.monotonic()
        if now - self._last_notify_ts.get(event, 0.0) < throttle_sec:
            return
        self._last_notify_ts[event] = now
        try:
            await notifier(text)
        except Exception:
            logger.exception("Failed to notify admin about AI event %s", event)

    def _get_current_model(self) -> str:
        """Return the current model based on rotation state, using healthy models only."""
        models = self.get_available_models()
        if self._rotate_every > 0 and len(models) > 1:
            idx = (self._process_count // self._rotate_every) % len(models)
            return models[idx]
        return models[0]

    def _get_fallback_models(self, failed_model: str) -> list[str]:
        """Return models to try as fallback, excluding failed/quota-exhausted ones.

        The chain is bounded by ``ai_max_fallback_attempts`` so an article never
        walks through 100+ models before giving up.
        """
        candidates = [m for m in self.get_available_models() if m != failed_model]
        candidates = candidates[: self._max_fallback_attempts]
        return candidates

    @staticmethod
    def _is_quota_error(err_str: str) -> bool:
        """Detect quota/rate-limit exhaustion from an error string."""
        lowered = err_str.lower()
        if "403" in err_str and ("quota" in lowered or "exhausted" in lowered):
            return True
        if "429" in err_str or "rate limit" in lowered or "quota" in lowered:
            return True
        return False

    def _mark_quota_exhausted(self, model: str) -> None:
        """Mark a model as quota-exhausted so we skip it for 30 minutes."""
        self._quota_exhausted[model] = int(time.monotonic())
        self._recently_failed.pop(model, None)
        logger.warning("Model %s marked as quota-exhausted, skipping for %d minutes", model, _QUOTA_COOLDOWN_SEC // 60)

    async def _mark_failed(self, model: str, err_str: str) -> None:
        """Record a model failure and alert the admin when relevant."""
        now = int(time.monotonic())
        self._recently_failed[model] = now
        is_quota = self._is_quota_error(err_str)
        if is_quota:
            self._mark_quota_exhausted(model)
        logger.warning("Model %s failed (%s), skipping for %ds", model, err_str[:80], _FAILED_COOLDOWN_SEC)
        if is_quota:
            await self._notify_admin(
                f"quota:{model}",
                f"⚠️ <b>AI model limiti tugadi:</b> <code>{html.escape(model, quote=False)}</code>\n"
                f"<i>{html.escape(err_str[:120], quote=False)}</i>",
            )

    def _advance_rotation(self) -> None:
        """Advance the process counter and rotate model if needed."""
        self._process_count += 1
        if self._rotate_every > 0 and len(self._models) > 1:
            models = self.get_available_models()
            old_idx = ((self._process_count - 1) // self._rotate_every) % len(models)
            new_idx = (self._process_count // self._rotate_every) % len(models)
            if old_idx != new_idx:
                logger.info("Model rotation: %s → %s (item #%d)",
                            models[old_idx], models[new_idx], self._process_count)

    async def _try_model(self, model: str, title: str, content: str) -> NewsAnalysis | None:
        """Try a single model for analysis. Returns None if it fails (so we can try next)."""
        try:
            self.primary.model = model
            analysis = await self.primary.analyze_news(title, content)

            # Post-process: translate any leaked non-Uzbek text and ensure title is set
            analysis = await self._post_process_analysis(analysis, title)
            # Model worked — clear any stale failure state so it stays in rotation
            self._recently_failed.pop(model, None)
            self._quota_exhausted.pop(model, None)
            return analysis
        except Exception as e:
            err_str = str(e)
            await self._mark_failed(model, err_str)
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
        await self._notify_admin(
            "all_models_failed",
            f"❌ <b>Barcha AI modellar muvaffaqiyatsiz!</b>\n\n"
            f"📰 <i>{html.escape(title[:80], quote=False)}</i>\n"
            f"🧠 Ro'yxatdagi modellar: {len(self._models)} ta\n"
            f"🔑 Tekshiring: API kalit, kvota, provayder holati.",
        )
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
        # Try each healthy model for digest (bounded fallback chain)
        model = self._get_current_model()
        fallback_models = self._get_fallback_models(model)

        for try_model in [model] + fallback_models:
            try:
                self.primary.model = try_model
                digest_items = await self.primary.generate_digest(news_items)

                if self.translator:
                    for item in digest_items:
                        text = item.get("text") or ""
                        if text and _needs_translation(text):
                            item["text"] = await self.translator.translate_to_uzbek(text)

                # Model worked — clear any stale failure state
                self._recently_failed.pop(try_model, None)
                self._quota_exhausted.pop(try_model, None)
                return digest_items
            except Exception as e:
                err_str = str(e)
                await self._mark_failed(try_model, err_str)
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

        await self._notify_admin(
            "digest_all_models_failed",
            "❌ <b>Digest yaratishda barcha AI modellar muvaffaqiyatsiz bo'ldi.</b>\n"
            "🔑 API kalit va kvota holatini tekshiring.",
        )
        return []
