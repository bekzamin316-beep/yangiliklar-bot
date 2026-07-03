"""AI Service for news analysis and digest generation."""

from typing import Dict, Any, Optional, List
import structlog
from app.core.database.repositories.ai_repository import AIRepository
from app.core.database.repositories.settings_repository import SettingsRepository
from app.ai.providers.base import BaseAIProvider

logger = structlog.get_logger(__name__)


class AIService:
    """Service for AI-powered news analysis and content generation."""

    def __init__(
        self,
        ai_repository: AIRepository,
        settings_repository: SettingsRepository,
        provider: BaseAIProvider,
    ):
        self.ai_repository = ai_repository
        self.settings_repository = settings_repository
        self.provider = provider
        self.logger = logger.bind(service="AIService")

    async def analyze_article(self, article_content: str) -> Optional[Dict[str, Any]]:
        """Analyze a news article using AI."""
        try:
            # Get news analysis prompt from database
            prompt_obj = await self.ai_repository.get_prompt("news_prompt")
            
            if not prompt_obj:
                # Default prompt if not in database
                prompt = """You are a crypto news analyst. Analyze the following news article and respond ONLY with valid JSON in this exact format:
{
    "title": "Brief title in Uzbek",
    "summary": "2-3 sentence summary in Uzbek",
    "analysis": "Detailed analysis in Uzbek (3-5 sentences)",
    "sentiment": "bullish or bearish or neutral",
    "importance_score": 0-100 (integer),
    "tags": ["tag1", "tag2"]
}

Translate everything to Uzbek language. Be concise but informative."""
            else:
                prompt = prompt_obj.template

            result = await self.provider.analyze_news(article_content, prompt)
            
            # Validate required fields
            if not all(key in result for key in ["title", "summary", "sentiment", "importance_score"]):
                self.logger.warning("AI response missing required fields", result=result)
                return None

            # Ensure importance_score is numeric
            if isinstance(result.get("importance_score"), str):
                try:
                    result["importance_score"] = float(result["importance_score"])
                except:
                    result["importance_score"] = 50

            # Ensure sentiment is valid
            valid_sentiments = ["bullish", "bearish", "neutral"]
            if result.get("sentiment", "").lower() not in valid_sentiments:
                result["sentiment"] = "neutral"

            return result

        except Exception as e:
            self.logger.error("Failed to analyze article", error=str(e))
            raise

    async def generate_daily_digest(
        self, news_items: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Generate daily digest from news items."""
        try:
            # Get digest prompt from database
            prompt_obj = await self.ai_repository.get_prompt("digest_prompt")
            
            if not prompt_obj:
                # Default prompt if not in database
                prompt = """You are a crypto news summarizer. Create a daily digest summary in Uzbek. Respond ONLY with valid JSON:
{
    "summary": "Overall market summary in Uzbek (2-3 sentences)",
    "most_bullish": "Most bullish event description in Uzbek",
    "most_bearish": "Most bearish event description in Uzbek"
}"""
            else:
                prompt = prompt_obj.template

            result = await self.provider.generate_digest(news_items, prompt)
            
            return result

        except Exception as e:
            self.logger.error("Failed to generate digest", error=str(e))
            raise

    async def test_provider(self) -> bool:
        """Test the current AI provider connection."""
        return await self.provider.test_connection()

    async def get_available_models(self) -> List[str]:
        """Get available models for current provider."""
        return await self.provider.get_available_models()

    def set_model(self, model_name: str):
        """Set the model to use for AI requests."""
        self.provider.model_name = model_name
