"""Manual test for OpenRouter provider."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.core.config import settings
from src.ai_service.summarizer import OpenRouterProvider


async def main():
    provider = OpenRouterProvider()
    print(f"API Base: {provider.api_base}")
    print(f"API Key length: {len(provider.api_key)}")
    print(f"API Key first 20 chars: {provider.api_key[:20]}")
    print(f"Model: {settings.ai_model}")
    try:
        result = await provider.generate("Hello, this is a test. Please respond.")
        print(f"Success: {result[:200]}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())