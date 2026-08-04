"""Publisher — sends news to Telegram channel."""

import html
import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

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

    async def publish_digest_message(
        self,
        title: str,
        news_count: int,
        ai_summary: str,
        telegraph_url: str,
        news_titles: list[str] | None = None,
    ) -> int | None:
        """Publish the short digest announcement to the channel.

        Per product requirements the channel only receives: digest title,
        news count, short AI summary, and the Telegraph page link.
        When ``news_titles`` is provided, the numbered bold title list is
        included before the summary.

        Returns the Telegram message_id, or None on failure.
        """
        lines = [
            title,
            "",
            f"📊 <b>{news_count} ta yangilik</b>",
            "",
        ]
        if news_titles:
            for t in news_titles:
                cleaned = str(t or "").strip()
                if cleaned:
                    lines.append(f"<b>{html.escape(cleaned)}</b>")
            lines.append("")
        if ai_summary:
            lines.append(html.escape(ai_summary))
            lines.append("")
        lines.append(f"📖 <a href=\"{telegraph_url}\">To'liq digest — Telegraph'da o'qing</a>")

        try:
            msg = await self.bot.send_message(
                chat_id=self.channel_id,
                text="\n".join(lines),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            logger.info("Published digest announcement (msg_id=%d, %d items)", msg.message_id, news_count)
            return msg.message_id
        except Exception as e:
            logger.error("Failed to publish digest announcement: %s", e)
            return None

    async def send_admin_notification(self, text: str) -> None:
        """Send a notification to all admin users.

        If an admin hasn't started a conversation with the bot,
        Telegram returns 'Bad Request: chat not found'.
        This is expected — we log it as a warning, not an error.
        """
        from aiogram.exceptions import TelegramBadRequest

        for admin_id in settings.admin_id_list:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except TelegramBadRequest as e:
                if "chat not found" in str(e).lower() or "bot can't initiate conversation" in str(e).lower():
                    logger.warning("Admin %d hasn't started bot yet — notification skipped", admin_id)
                else:
                    logger.error("Failed to notify admin %d: %s", admin_id, e)
            except Exception as e:
                logger.error("Failed to notify admin %d: %s", admin_id, e)

    async def edit_message_text(self, message_id: int, text: str) -> bool:
        """Edit an existing message.

        Args:
            message_id: ID of the message to edit
            text: New text content

        Returns True if successful.
        """
        try:
            await self.bot.edit_message_text(
                chat_id=self.channel_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            logger.info("Edited message (msg_id=%d)", message_id)
            return True
        except TelegramBadRequest as e:
            logger.error("Failed to edit message %d: %s", message_id, e)
            return False
        except Exception as e:
            logger.error("Unexpected error editing message %d: %s", message_id, e)
            return False
