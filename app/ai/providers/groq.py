"""Groq AI Provider implementation."""

from typing import Dict, Any, List
from app.ai.providers.base import BaseAIProvider


class GroqProvider(BaseAIProvider):
    """Groq AI provider implementation."""

    def __init__(self, api_key: str = None, base_url: str = "https://api.groq.com/openai/v1"):
        super().__init__(api_key, base_url)

    @property
    def name(self) -> str:
        return "groq"

    async def analyze_news(self, content: str, prompt: str) -> Dict[str, Any]:
        """Analyze news article using Groq."""
        payload = {
            "model": self.model_name or "llama3-70b-8192",
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
        }

        response = await self._make_request("/chat/completions", payload, headers)
        return self._parse_response(response)

    async def generate_digest(self, news_items: List[Dict], prompt: str) -> Dict[str, Any]:
        """Generate daily digest using Groq."""
        news_text = "\n\n".join([
            f"{i+1}. {item.get('title', '')}\n   Summary: {item.get('summary', '')}"
            for i, item in enumerate(news_items)
        ])

        payload = {
            "model": self.model_name or "llama3-70b-8192",
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
        }

        response = await self._make_request("/chat/completions", payload, headers)
        return self._parse_response(response)

    async def test_connection(self) -> bool:
        """Test Groq connection."""
        try:
            payload = {
                "model": "llama3-70b-8192",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10,
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            await self._make_request("/chat/completions", payload, headers)
            return True
        except Exception as e:
            self.logger.error("Groq connection test failed", error=str(e))
            return False

    async def get_available_models(self) -> List[str]:
        """Get available models from Groq."""
        return [
            "llama3-70b-8192",
            "llama3-8b-8192",
            "mixtral-8x7b-32768",
            "gemma-7b-it",
        ]
