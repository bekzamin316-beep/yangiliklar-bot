"""Publisher — sends news to Telegram channel."""

import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import NewsRepository
from src.news_collector.processor import NewsProcessor

logger = logging.getLogger(__name__)


class Publisher:
    """Publishes news to the Telegram channel."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.channel_id = settings.telegram_channel_id

    async def publish_news(self, news) -> bool:
        """Publish a single news item to the channel.

        Returns True if published successfully.
        """
        text = NewsProcessor.format_post(news)

        try:
            msg = await self.bot.send_message(
                chat_id=self.channel_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

            # Mark as published in DB
            async with get_session() as session:
                repo = NewsRepository(session)
                await repo.update(news.id, is_published=True, channel_message_id=msg.message_id)

            logger.info("Published: %s (msg_id=%d)", news.title[:50], msg.message_id)
            return True

        except Exception as e:
            logger.error("Failed to publish %s: %s", news.title[:50], e)
            return False

    async def publish_batch(self, news_items: list, max_items: int = 10) -> int:
        """Publish a batch of news items.

        Returns the count of successfully published items.
        """
        published = 0
        for news in news_items[:max_items]:
            if await self.publish_news(news):
                published += 1
        logger.info("Published %d/%d items", published, len(news_items))
        return published

    async def publish_digest(self, digest_text: str) -> bool:
        """Publish a daily digest to the channel."""
        try:
            msg = await self.bot.send_message(
                chat_id=self.channel_id,
                text=digest_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            logger.info("Published digest (msg_id=%d)", msg.message_id)
            return True
        except Exception as e:
            logger.error("Failed to publish digest: %s", e)
            return False

    async def send_admin_notification(self, text: str) -> None:
        """Send a notification to all admin users."""
        for admin_id in settings.admin_id_list:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.error("Failed to notify admin %d: %s", admin_id, e)
