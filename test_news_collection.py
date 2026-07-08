"""Manual test for news collection."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.core.logging_config import setup_logging
from src.core.database import init_db, close_db
from src.scheduler.jobs import collect_and_publish_news
from src.telegram_bot.bot import create_bot
from src.telegram_bot.publisher import Publisher


async def main():
    setup_logging()
    await init_db()
    bot = create_bot()
    publisher = Publisher(bot)
    await collect_and_publish_news(publisher)
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())