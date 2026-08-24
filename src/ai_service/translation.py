"""Translation utilities for AI responses."""

import logging
import re

from src.ai_service.prompt_loader import load_prompt
from src.ai_service.summarizer import DashScopeProvider, OmniRouteProvider, OpenRouterProvider
from src.core.config import settings

logger = logging.getLogger(__name__)

# Keeps the trailing punctuation with the sentence when splitting.
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")


class TranslationService:
    """Handles translation of AI responses to Uzbek — uses the configured AI provider.

    The provider and model chain mirrors the analysis chain: primary → backup →
    any other provider that has valid credentials (e.g. DashScope when OpenRouter
    is rate-limited). Each provider tries its model(s) in turn, so a single
    dead/rate-limited model or key can never silently break translations again.
    """

    def __init__(self):
        # Order of preference: configured primary → configured backup → any
        # other provider with valid credentials. Providers without a key are
        # skipped, and duplicates are collapsed.
        names = [settings.ai_provider]
        if settings.ai_backup_provider and settings.ai_backup_provider not in names:
            names.append(settings.ai_backup_provider)
        for candidate in ("dashscope", "openrouter"):
            if candidate not in names:
                names.append(candidate)
        # OmniRoute is self-hosted with optional auth — only auto-add it when
        # explicitly keyed, so a dead/unconfigured router never adds latency.
        if settings.omniroute_api_key and "omniroute" not in names:
            names.append("omniroute")

        self.providers: list = []
        for name in names:
            provider = self._build_provider(name)
            if provider and all(type(p) is not type(provider) for p in self.providers):
                self.providers.append(provider)

    @staticmethod
    def _build_provider(provider_name: str):
        """Instantiate a provider by name, or None when it lacks credentials."""
        if provider_name == "openrouter":
            if not settings.openrouter_api_key:
                return None
            return OpenRouterProvider()
        if provider_name == "omniroute":
            return OmniRouteProvider()
        if provider_name == "dashscope":
            if not settings.dashscope_api_key:
                return None
            return DashScopeProvider()
        return None

    @staticmethod
    def _models_for(provider) -> list[str]:
        """Return the model(s) to try for a given provider."""
        if isinstance(provider, DashScopeProvider):
            return [settings.ai_model_backup or "qwen-plus"]
        if isinstance(provider, OmniRouteProvider):
            return [settings.ai_model_backup or settings.ai_model]
        return settings.ai_models_list or [settings.ai_model]

    # Chars per request chunk (~600 tokens). Small enough that the translated
    # output always fits inside a modest max_tokens budget, big enough to keep
    # the number of API calls low.
    _CHUNK_CHARS = 2500

    async def translate_to_uzbek(self, text: str) -> str:
        """Translate text from any language to Uzbek using AI.

        Long texts are split into sentence-boundary chunks and each chunk is
        translated separately, so articles of any length come back complete
        instead of being cut off by the model's token limit. Falls back across
        the configured providers and models per chunk.
        """
        if not text.strip():
            return text

        system = "Siz professional tarjimon. Barcha tarjimalar o'zbek tilida (Lotin alifbosi) bo'lishi shart."
        chunks = self._split_chunks(text)

        if len(chunks) == 1:
            result = await self._translate_chunk(chunks[0], system)
            return result if result is not None else text

        parts: list[str] = []
        for n, chunk in enumerate(chunks, 1):
            logger.info("Translating chunk %d/%d (%d chars)", n, len(chunks), len(chunk))
            result = await self._translate_chunk(chunk, system)
            if result is None:
                # Keep the original chunk so the final text stays complete
                # rather than silently losing content.
                logger.error("Chunk %d/%d failed on all providers — keeping original", n, len(chunks))
                parts.append(chunk)
            else:
                parts.append(result)
        return "\n\n".join(parts)

    async def _translate_chunk(self, text: str, system: str) -> str | None:
        """Translate one chunk via the provider chain. None when all fail."""
        # Use replace() instead of .format() so translated text containing
        # braces (e.g. JSON, code) never crashes the prompt builder.
        prompt = load_prompt("translate").replace("{text}", text)

        # Scale the output budget with the source length (~4 chars/token plus
        # headroom). Without this the provider default of 1024 tokens truncates
        # long chunks mid-sentence.
        max_tokens = min(4000, max(1024, len(text)))

        for i, provider in enumerate(self.providers):
            for model in self._models_for(provider):
                try:
                    provider.model = model
                    translated = await provider.generate(prompt, system=system, max_tokens=max_tokens)
                    result = translated.strip()
                    if result:
                        return result
                except Exception as e:
                    logger.warning(
                        "Translation provider %d/%d (%s, model %s) failed: %s",
                        i + 1, len(self.providers), type(provider).__name__, model, e,
                    )

        logger.error("All translation providers failed for text: %s", text[:80])
        return None

    @classmethod
    def _split_chunks(cls, text: str) -> list[str]:
        """Split text into <=_CHUNK_CHARS pieces at paragraph/sentence borders."""
        if len(text) <= cls._CHUNK_CHARS:
            return [text]

        chunks: list[str] = []
        current = ""
        # Prefer paragraph boundaries, then sentences, then hard splits.
        for piece in text.split("\n"):
            while len(piece) > cls._CHUNK_CHARS:
                piece = piece.strip()
                sentences = _SENTENCE_RE.split(piece)
                buf = ""
                for s in sentences:
                    if buf and len(buf) + len(s) + 1 > cls._CHUNK_CHARS:
                        chunks.append(buf.strip())
                        buf = ""
                    while len(s) > cls._CHUNK_CHARS:
                        # Single monster sentence — hard split mid-sentence.
                        head, s = s[:cls._CHUNK_CHARS], s[cls._CHUNK_CHARS:]
                        if buf:
                            chunks.append(buf.strip())
                            buf = ""
                        chunks.append(head)
                    buf += (" " if buf else "") + s
                piece = buf

            candidate = f"{current}\n{piece}".strip() if current else piece.strip()
            if len(candidate) > cls._CHUNK_CHARS and current:
                chunks.append(current)
                current = piece.strip()
            else:
                current = candidate
        if current.strip():
            chunks.append(current.strip())
        return [c for c in chunks if c]

    async def warmup_check(self) -> bool:
        """Health check — verifies at least one provider can translate."""
        test = "test"
        result = await self.translate_to_uzbek(test)
        return result.lower() != "test"
