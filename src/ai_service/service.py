"""High-level AI service with retry, model-level fallback, and rotation."""

import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.ai_service.models import NewsAnalysis
from src.ai_service.summarizer import DashScopeProvider, OpenRouterProvider
from src.ai_service.translation import TranslationService

logger = logging.getLogger(__name__)


class AIService:
    """AI service with model-level fallback — tries each model before giving up."""

    def __init__(self):
        # Choose provider based on config
        if settings.ai_provider == "openrouter":
            self.primary = OpenRouterProvider()
        else:
            self.primary = DashScopeProvider()

        # Backup provider (if configured)
        if settings.ai_backup_api_key:
            if settings.ai_backup_provider == "openrouter":
                self.backup = OpenRouterProvider()
            else:
                self.backup = DashScopeProvider()
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

    def _get_current_model(self) -> str:
        """Return the current model based on rotation state."""
        if self._rotate_every > 0 and len(self._models) > 1:
            idx = (self._process_count // self._rotate_every) % len(self._models)
            return self._models[idx]
        return self._models[0]

    def _get_fallback_models(self, failed_model: str) -> list[str]:
        """Return models to try as fallback, excluding the failed one and quota-exhausted ones."""
        candidates = [m for m in self._models if m != failed_model]
        # Also skip models that recently hit quota limits (within last 30 minutes)
        import time
        now = int(time.monotonic())
        recent_exhausted = [m for m, ts in self._quota_exhausted.items() if now - ts < 1800]
        if recent_exhausted:
            logger.info("Skipping recently quota-exhausted models: %s", recent_exhausted)
            candidates = [m for m in candidates if m not in recent_exhausted]
        return candidates

    def _mark_quota_exhausted(self, model: str) -> None:
        """Mark a model as quota-exhausted so we skip it for 30 minutes."""
        import time
        self._quota_exhausted[model] = int(time.monotonic())
        logger.warning("Model %s marked as quota-exhausted, skipping for 30 minutes", model)

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
        try:
            self.primary.model = model
            analysis = await self.primary.analyze_news(title, content)

            # Translate if enabled
            if self.translator and analysis.summary_uz:
                analysis.summary_uz = await self.translator.translate_to_uzbek(analysis.summary_uz)
                analysis.analysis_uz = await self.translator.translate_to_uzbek(analysis.analysis_uz)

            return analysis
        except Exception as e:
            err_str = str(e)
            # Detect quota exhaustion (403 with "free quota has been exhausted")
            if "403" in err_str and ("quota" in err_str.lower() or "exhausted" in err_str.lower()):
                self._mark_quota_exhausted(model)
            logger.warning("Model %s failed: %s", model, err_str[:100])
            return None

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

                if self.translator and analysis.summary_uz:
                    analysis.summary_uz = await self.translator.translate_to_uzbek(analysis.summary_uz)
                    analysis.analysis_uz = await self.translator.translate_to_uzbek(analysis.analysis_uz)

                self._advance_rotation()
                return analysis
            except Exception as e2:
                logger.error("Backup AI provider also failed: %s", e2)

        # Step 4: Minimal analysis with translation fallback
        self._advance_rotation()
        logger.warning("All models failed for: %s — returning minimal analysis", title[:50])
        fallback_summary = title[:200]
        if self.translator:
            try:
                fallback_summary = await self.translator.translate_to_uzbek(fallback_summary)
            except Exception as te:
                logger.error("Fallback translation also failed: %s", te)
        return NewsAnalysis(
            summary_uz=fallback_summary,
            analysis_uz="Yangilik tavsifi mavjud emas.",
            importance_score=50,
            sentiment="neutral",
        )

    async def create_digest(self, news_items: list[dict]) -> dict:
        """Generate a daily digest with model-level fallback."""
        # Try each model for digest
        model = self._get_current_model()
        fallback_models = self._get_fallback_models(model)

        for try_model in [model] + fallback_models:
            try:
                self.primary.model = try_model
                digest = await self.primary.generate_digest(news_items)

                if self.translator:
                    for key in ["summary", "most_bullish", "most_bearish"]:
                        if digest.get(key):
                            digest[key] = await self.translator.translate_to_uzbek(digest[key])

                return digest
            except Exception as e:
                err_str = str(e)
                if "403" in err_str and ("quota" in err_str.lower() or "exhausted" in err_str.lower()):
                    self._mark_quota_exhausted(try_model)
                logger.warning("Digest model %s failed: %s", try_model, err_str[:100])

        # Backup provider
        if self.backup:
            try:
                digest = await self.backup.generate_digest(news_items)
                if self.translator:
                    for key in ["summary", "most_bullish", "most_bearish"]:
                        if digest.get(key):
                            digest[key] = await self.translator.translate_to_uzbek(digest[key])
                return digest
            except Exception as e2:
                logger.error("Backup digest also failed: %s", e2)

        return {
            "summary": "Bugun kriptovalyuta bozorida turli xil yangiliklar bo'ldi.",
            "most_bullish": "",
            "most_bearish": "",
        }
