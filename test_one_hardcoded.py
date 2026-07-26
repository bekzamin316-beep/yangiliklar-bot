"""Test: analyze and publish a hardcoded single news item."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.core.logging_config import setup_logging
from src.core.database import init_db, close_db
from src.ai_service.service import AIService
from src.news_collector.models import RawNewsItem
from src.news_collector.processor import NewsProcessor
from src.telegram_bot.bot import create_bot
from src.telegram_bot.publisher import Publisher


async def main():
    setup_logging()
    await init_db()

    item = RawNewsItem(
        title="Bitcoin advocacy group to join US State Department's digital asset talks",
        content=(
            "A Bitcoin advocacy group has been invited to participate in the US State "
            "Department's upcoming digital asset policy discussions on July 26, 2026. The meeting is "
            "expected to address regulatory clarity for cryptocurrencies and stablecoins, "
            "as well as the role of Bitcoin in national financial strategy. Industry "
            "observers view the invitation as a sign of growing mainstream acceptance of "
            "digital assets in Washington."
        ),
        url=f"https://example.com/bitcoin-state-dept-{datetime.now(timezone.utc).timestamp()}",
        source_name="TestSource",
        published_at=datetime.now(timezone.utc),
    )

    print(f"Test yangilik: {item.title}")

    bot = create_bot()
    publisher = Publisher(bot)

    ai_service = AIService()
    processor = NewsProcessor(ai_service)

    analysis = await ai_service.analyze_news(item.title, item.content)
    print(f"AI javobi:\n  title_uz={analysis.title_uz}")
    print(f"  summary_uz={analysis.summary_uz}")
    print(f"  analysis_uz={analysis.analysis_uz}")
    print(f"  sentiment={analysis.sentiment}, score={analysis.importance_score}")
    print(f"  tags={analysis.tags}")

    news = await processor._save_news(item, analysis)
    print(f"DBga saqlandi: id={news.id}")

    published = await publisher.publish_news(news)
    print(f"Telegramga yuborildi: {published}")

    await bot.session.close()
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
