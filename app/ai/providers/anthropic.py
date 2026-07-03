"""Anthropic Claude AI Provider implementation."""

from typing import Dict, Any, List
import aiohttp
from app.ai.providers.base import BaseAIProvider


class AnthropicProvider(BaseAIProvider):
    """Anthropic Claude AI provider implementation."""

    def __init__(self, api_key: str = None, base_url: str = "https://api.anthropic.com/v1"):
        super().__init__(api_key, base_url)

    @property
    def name(self) -> str:
        return "anthropic"

    async def analyze_news(self, content: str, prompt: str) -> Dict[str, Any]:
        """Analyze news article using Claude."""
        model_name = self.model_name or "claude-3-opus-20240229"
        
        payload = {
            "model": model_name,
            "max_tokens": 1024,
            "system": "You are a crypto news analyst. Respond in JSON format.",
            "messages": [
                {"role": "user", "content": f"{prompt}\n\nArticle:\n{content}"}
            ]
        }

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        response = await self._make_request("/messages", payload, headers)
        return self._parse_claude_response(response)

    async def generate_digest(self, news_items: List[Dict], prompt: str) -> Dict[str, Any]:
        """Generate daily digest using Claude."""
        model_name = self.model_name or "claude-3-opus-20240229"
        
        news_text = "\n\n".join([
            f"{i+1}. {item.get('title', '')}\n   Summary: {item.get('summary', '')}"
            for i, item in enumerate(news_items)
        ])

        payload = {
            "model": model_name,
            "max_tokens": 2048,
            "system": "You are a crypto news summarizer. Respond in JSON format.",
            "messages": [
                {"role": "user", "content": f"{prompt}\n\nNews Items:\n{news_text}"}
            ]
        }

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        response = await self._make_request("/messages", payload, headers)
        return self._parse_claude_response(response)

    async def test_connection(self) -> bool:
        """Test Anthropic connection."""
        try:
            payload = {
                "model": "claude-3-opus-20240229",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "test"}]
            }

            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            }

            await self._make_request("/messages", payload, headers)
            return True
        except Exception as e:
            self.logger.error("Anthropic connection test failed", error=str(e))
            return False

    async def get_available_models(self) -> List[str]:
        """Get available models from Anthropic."""
        return [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ]

    def _parse_claude_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Claude API response."""
        content = response.get("content", [{}])[0].get("text", "")
        
        try:
            import json
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                return json.loads(json_str)
        except:
            pass
        
        return {"raw": content}
