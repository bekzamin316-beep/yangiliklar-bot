"""Fallback AI Service with automatic provider failover."""

from typing import Dict, Any, Optional, List
import structlog
from app.core.database.repositories.ai_repository import AIRepository
from app.core.database.repositories.settings_repository import SettingsRepository
from app.ai.providers.base import BaseAIProvider
from app.ai.providers.openrouter import OpenRouterProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.ollama import OllamaProvider

logger = structlog.get_logger(__name__)


class FallbackAIService:
    """AI Service with automatic fallback to backup providers."""

    PROVIDER_CLASSES = {
        "openrouter": OpenRouterProvider,
        "groq": GroqProvider,
        "gemini": GeminiProvider,
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
    }

    def __init__(
        self,
        ai_repository: AIRepository,
        settings_repository: SettingsRepository,
    ):
        self.ai_repository = ai_repository
        self.settings_repository = settings_repository
        self.logger = logger.bind(service="FallbackAIService")
        self.current_provider: Optional[BaseAIProvider] = None
        self.model_name: Optional[str] = None

    async def _get_provider_instance(self, provider_name: str) -> Optional[BaseAIProvider]:
        """Get provider instance by name."""
        if provider_name not in self.PROVIDER_CLASSES:
            return None

        provider_class = self.PROVIDER_CLASSES[provider_name]
        
        # Get API key from settings or environment
        api_key = await self.settings_repository.get_value(f"{provider_name}_api_key")
        base_url = await self.settings_repository.get_value(f"{provider_name}_base_url")

        if not api_key and provider_name != "ollama":
            self.logger.warning(f"No API key for {provider_name}")
            return None

        return provider_class(api_key=api_key, base_url=base_url)

    async def _get_provider_order(self) -> List[str]:
        """Get ordered list of providers to try."""
        # Try to get fallback order from database
        fallback_order = await self.settings_repository.get_value("ai_fallback_order")
        
        if fallback_order:
            return fallback_order
        
        # Default fallback order
        return ["openrouter", "groq", "gemini", "anthropic", "openai", "ollama"]

    async def analyze_article(self, article_content: str) -> Optional[Dict[str, Any]]:
        """Analyze article with automatic fallback."""
        provider_order = await self._get_provider_order()
        
        for provider_name in provider_order:
            try:
                self.logger.info(f"Trying provider: {provider_name}")
                
                provider = await self._get_provider_instance(provider_name)
                if not provider:
                    continue

                provider.model_name = self.model_name
                
                # Create temporary AIService with this provider
                from app.ai.services.ai_service import AIService
                ai_service = AIService(
                    self.ai_repository,
                    self.settings_repository,
                    provider,
                )
                
                result = await ai_service.analyze_article(article_content)
                
                if result:
                    self.current_provider = provider
                    self.logger.info(f"Successfully analyzed with {provider_name}")
                    
                    # Record successful request
                    provider_db = await self.ai_repository.get_provider_by_name(provider_name)
                    if provider_db:
                        await self.ai_repository.record_request(provider_db.id)
                    
                    return result
                    
            except Exception as e:
                self.logger.error(f"Provider {provider_name} failed", error=str(e))
                
                # Record error
                provider_db = await self.ai_repository.get_provider_by_name(provider_name)
                if provider_db:
                    await self.ai_repository.record_error(provider_db.id, str(e))
                
                continue
        
        self.logger.error("All AI providers failed")
        raise Exception("All AI providers failed to analyze the article")

    async def generate_daily_digest(
        self, news_items: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Generate digest with automatic fallback."""
        provider_order = await self._get_provider_order()
        
        for provider_name in provider_order:
            try:
                self.logger.info(f"Trying provider: {provider_name} for digest")
                
                provider = await self._get_provider_instance(provider_name)
                if not provider:
                    continue

                provider.model_name = self.model_name
                
                from app.ai.services.ai_service import AIService
                ai_service = AIService(
                    self.ai_repository,
                    self.settings_repository,
                    provider,
                )
                
                result = await ai_service.generate_daily_digest(news_items)
                
                if result:
                    self.current_provider = provider
                    self.logger.info(f"Successfully generated digest with {provider_name}")
                    
                    provider_db = await self.ai_repository.get_provider_by_name(provider_name)
                    if provider_db:
                        await self.ai_repository.record_request(provider_db.id)
                    
                    return result
                    
            except Exception as e:
                self.logger.error(f"Provider {provider_name} failed for digest", error=str(e))
                
                provider_db = await self.ai_repository.get_provider_by_name(provider_name)
                if provider_db:
                    await self.ai_repository.record_error(provider_db.id, str(e))
                
                continue
        
        self.logger.error("All AI providers failed for digest")
        raise Exception("All AI providers failed to generate digest")

    def set_model(self, model_name: str):
        """Set the model to use."""
        self.model_name = model_name

    async def test_all_providers(self) -> Dict[str, bool]:
        """Test all available providers."""
        results = {}
        
        for provider_name in self.PROVIDER_CLASSES.keys():
            try:
                provider = await self._get_provider_instance(provider_name)
                if provider:
                    is_working = await provider.test_connection()
                    results[provider_name] = is_working
                else:
                    results[provider_name] = False
            except Exception as e:
                self.logger.error(f"Failed to test {provider_name}", error=str(e))
                results[provider_name] = False
        
        return results
