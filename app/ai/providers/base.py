"""Base AI Provider interface."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import structlog

logger = structlog.get_logger(__name__)


class BaseAIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url
        self.logger = logger.bind(provider=self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        pass

    @abstractmethod
    async def analyze_news(self, content: str, prompt: str) -> Dict[str, Any]:
        """Analyze news article and return structured data."""
        pass

    @abstractmethod
    async def generate_digest(self, news_items: List[Dict], prompt: str) -> Dict[str, Any]:
        """Generate daily digest from news items."""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test provider connection and API key validity."""
        pass

    @abstractmethod
    async def get_available_models(self) -> List[str]:
        """Get list of available models for this provider."""
        pass

    async def _make_request(
        self, endpoint: str, payload: Dict[str, Any], headers: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to AI provider API."""
        import aiohttp
        
        url = f"{self.base_url}/{endpoint}" if self.base_url else endpoint
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"API request failed: {response.status}", error=error_text)
                    raise Exception(f"API Error {response.status}: {error_text}")
                
                return await response.json()

    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse AI response into structured format."""
        # Default implementation - override in subclasses
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        try:
            import json
            # Try to extract JSON from response
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                return json.loads(json_str)
        except:
            pass
        
        # Return raw content if JSON parsing fails
        return {"raw": content}
