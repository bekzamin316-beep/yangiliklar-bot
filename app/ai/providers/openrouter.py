"""OpenRouter AI Provider implementation."""

from typing import Dict, Any, List
import json
from app.ai.providers.base import BaseAIProvider


class OpenRouterProvider(BaseAIProvider):
    """OpenRouter AI provider implementation."""

    def __init__(self, api_key: str = None, base_url: str = "https://openrouter.ai/api/v1"):
        super().__init__(api_key, base_url)

    @property
    def name(self) -> str:
        return "openrouter"

    async def analyze_news(self, content: str, prompt: str) -> Dict[str, Any]:
        """Analyze news article using OpenRouter."""
        payload = {
            "model": self.model_name or "meta-llama/llama-3-70b-instruct",
            "messages": [
                {"role": "system", "content": "You are a crypto news analyst. Respond in JSON format."},
                {"role": "user", "content": f"{prompt}\n\nArticle:\n{content}"}
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://crypto-news-bot",
        }

        response = await self._make_request("/chat/completions", payload, headers)
        return self._parse_response(response)

    async def generate_digest(self, news_items: List[Dict], prompt: str) -> Dict[str, Any]:
        """Generate daily digest using OpenRouter."""
        news_text = "\n\n".join([
            f"{i+1}. {item.get('title', '')}\n   Summary: {item.get('summary', '')}"
            for i, item in enumerate(news_items)
        ])

        payload = {
            "model": self.model_name or "meta-llama/llama-3-70b-instruct",
            "messages": [
                {"role": "system", "content": "You are a crypto news summarizer. Respond in JSON format."},
                {"role": "user", "content": f"{prompt}\n\nNews Items:\n{news_text}"}
            ],
            "temperature": 0.5,
            "max_tokens": 2048,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://crypto-news-bot",
        }

        response = await self._make_request("/chat/completions", payload, headers)
        return self._parse_response(response)

    async def test_connection(self) -> bool:
        """Test OpenRouter connection."""
        try:
            payload = {
                "model": "meta-llama/llama-3-70b-instruct",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10,
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://crypto-news-bot",
            }

            await self._make_request("/chat/completions", payload, headers)
            return True
        except Exception as e:
            self.logger.error("OpenRouter connection test failed", error=str(e))
            return False

    async def get_available_models(self) -> List[str]:
        """Get available models from OpenRouter."""
        try:
            import aiohttp
            
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/models", headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = data.get("data", [])
                        return [model.get("id") for model in models]
        except Exception as e:
            self.logger.error("Failed to fetch OpenRouter models", error=str(e))
        
        # Return default models if API call fails
        return [
            "meta-llama/llama-3-70b-instruct",
            "meta-llama/llama-3-8b-instruct",
            "google/gemma-7b-it",
            "mistralai/mistral-large",
            "anthropic/claude-3-opus",
            "openai/gpt-4-turbo",
        ]
