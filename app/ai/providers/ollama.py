"""Ollama Local AI Provider implementation."""

from typing import Dict, Any, List
import aiohttp
from app.ai.providers.base import BaseAIProvider


class OllamaProvider(BaseAIProvider):
    """Ollama local AI provider implementation."""

    def __init__(self, api_key: str = None, base_url: str = "http://ollama:11434"):
        super().__init__(api_key, base_url)

    @property
    def name(self) -> str:
        return "ollama"

    async def analyze_news(self, content: str, prompt: str) -> Dict[str, Any]:
        """Analyze news article using Ollama."""
        model_name = self.model_name or "llama3"
        
        payload = {
            "model": model_name,
            "prompt": f"{prompt}\n\nArticle:\n{content}",
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 1024,
            }
        }

        response = await self._make_request("/api/generate", payload)
        return self._parse_ollama_response(response)

    async def generate_digest(self, news_items: List[Dict], prompt: str) -> Dict[str, Any]:
        """Generate daily digest using Ollama."""
        model_name = self.model_name or "llama3"
        
        news_text = "\n\n".join([
            f"{i+1}. {item.get('title', '')}\n   Summary: {item.get('summary', '')}"
            for i, item in enumerate(news_items)
        ])

        payload = {
            "model": model_name,
            "prompt": f"{prompt}\n\nNews Items:\n{news_text}",
            "stream": False,
            "options": {
                "temperature": 0.5,
                "num_predict": 2048,
            }
        }

        response = await self._make_request("/api/generate", payload)
        return self._parse_ollama_response(response)

    async def test_connection(self) -> bool:
        """Test Ollama connection."""
        try:
            payload = {
                "model": "llama3",
                "prompt": "test",
                "stream": False,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/api/generate", json=payload) as response:
                    return response.status == 200
        except Exception as e:
            self.logger.error("Ollama connection test failed", error=str(e))
            return False

    async def get_available_models(self) -> List[str]:
        """Get available models from Ollama."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    if response.status == 200:
                        data = await response.json()
                        models = data.get("models", [])
                        return [model.get("name") for model in models]
        except Exception as e:
            self.logger.error("Failed to fetch Ollama models", error=str(e))
        
        # Return default models if API call fails
        return [
            "llama3",
            "llama3:70b",
            "mistral",
            "mixtral",
            "gemma",
        ]

    def _parse_ollama_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Ollama API response."""
        content = response.get("response", "")
        
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
