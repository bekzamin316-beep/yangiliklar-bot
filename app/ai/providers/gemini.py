"""Google Gemini AI Provider implementation."""

from typing import Dict, Any, List
import aiohttp
from app.ai.providers.base import BaseAIProvider


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI provider implementation."""

    def __init__(self, api_key: str = None, base_url: str = "https://generativelanguage.googleapis.com/v1beta"):
        super().__init__(api_key, base_url)

    @property
    def name(self) -> str:
        return "gemini"

    async def analyze_news(self, content: str, prompt: str) -> Dict[str, Any]:
        """Analyze news article using Gemini."""
        model_name = self.model_name or "gemini-1.5-flash"
        url = f"{self.base_url}/models/{model_name}:generateContent?key={self.api_key}"
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"{prompt}\n\nArticle:\n{content}"
                }]
            }],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 1024,
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Gemini API Error {response.status}: {error_text}")
                
                result = await response.json()
                content_text = result["candidates"][0]["content"]["parts"][0]["text"]
                
                try:
                    import json
                    start_idx = content_text.find("{")
                    end_idx = content_text.rfind("}") + 1
                    if start_idx >= 0 and end_idx > start_idx:
                        return json.loads(content_text[start_idx:end_idx])
                except:
                    pass
                
                return {"raw": content_text}

    async def generate_digest(self, news_items: List[Dict], prompt: str) -> Dict[str, Any]:
        """Generate daily digest using Gemini."""
        model_name = self.model_name or "gemini-1.5-flash"
        url = f"{self.base_url}/models/{model_name}:generateContent?key={self.api_key}"
        
        news_text = "\n\n".join([
            f"{i+1}. {item.get('title', '')}\n   Summary: {item.get('summary', '')}"
            for i, item in enumerate(news_items)
        ])

        payload = {
            "contents": [{
                "parts": [{
                    "text": f"{prompt}\n\nNews Items:\n{news_text}"
                }]
            }],
            "generationConfig": {
                "temperature": 0.5,
                "maxOutputTokens": 2048,
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Gemini API Error {response.status}: {error_text}")
                
                result = await response.json()
                content_text = result["candidates"][0]["content"]["parts"][0]["text"]
                
                try:
                    import json
                    start_idx = content_text.find("{")
                    end_idx = content_text.rfind("}") + 1
                    if start_idx >= 0 and end_idx > start_idx:
                        return json.loads(content_text[start_idx:end_idx])
                except:
                    pass
                
                return {"raw": content_text}

    async def test_connection(self) -> bool:
        """Test Gemini connection."""
        try:
            model_name = "gemini-1.5-flash"
            url = f"{self.base_url}/models/{model_name}:generateContent?key={self.api_key}"
            
            payload = {
                "contents": [{
                    "parts": [{"text": "test"}]
                }]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    return response.status == 200
        except Exception as e:
            self.logger.error("Gemini connection test failed", error=str(e))
            return False

    async def get_available_models(self) -> List[str]:
        """Get available models from Gemini."""
        return [
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.0-pro",
        ]
