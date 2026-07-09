"""Crypto price fetcher job — runs periodically to update pinned message."""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram.enums import ParseMode

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import SettingsRepository
from src.crypto_prices.service import CryptoPriceService
from src.telegram_bot.bot import Bot

logger = logging.getLogger(__name__)


class LivePriceService:
    """Manages live crypto price display in channel."""

    def __init__(self):
        self.bot = Bot(token=settings.telegram_bot_token)
        self.channel_id = int(settings.telegram_channel_id)
        self.service = CryptoPriceService()
        self.message_id: int | None = None

    async def _load_message_id(self) -> None:
        """Load persisted message_id from DB."""
        async with get_session() as session:
            repo = SettingsRepository(session)
            mid = await repo.get_value("live_price_message_id")
            if mid:
                self.message_id = int(mid)

    async def _save_message_id(self) -> None:
        """Persist current message_id to DB."""
        async with get_session() as session:
            repo = SettingsRepository(session)
            await repo.set_value("live_price_message_id", str(self.message_id))

    async def get_configured_coins(self) -> list[str]:
        """Get list of coins from settings, default to BTC, ETH, SOL."""
        async with get_session() as session:
            repo = SettingsRepository(session)
            coins_str = await repo.get_value("live_price_coins")
            if coins_str:
                return [c.strip() for c in coins_str.split(",") if c.strip()]
        # Default coins
        return ["bitcoin", "ethereum", "solana", "binancecoin", "ripple"]

    async def get_update_interval(self) -> int:
        """Get update interval in seconds, default to 60."""
        async with get_session() as session:
            repo = SettingsRepository(session)
            interval = await repo.get_int("live_price_interval", 60)
        return max(15, interval)  # Minimum 15 seconds

    async def format_price_message(self, coin_ids: list[str]) -> str:
        """Format the price display message."""
        try:
            from zoneinfo import ZoneInfo

            prices = await self.service.fetch_prices(coin_ids)
            tz = ZoneInfo("Asia/Tashkent")
            now = datetime.now(tz)

            lines = []

            for coin_id in coin_ids:
                if coin_id in prices:
                    data = prices[coin_id]
                    name = self.service.get_display_name(coin_id)
                    price = self.service.format_price(data["price"], coin_id)
                    change = self.service.format_change(data["change_24h"])
                    lines.append(f"<b>{name}</b>")
                    lines.append(f"└ {price}  {change}")
                else:
                    lines.append(f"<b>{coin_id}</b>")
                    lines.append("└ ---  ---")

            lines.append("")
            lines.append(f"🕐 <i>Yangilangan: {now.strftime('%H:%M:%S')} (Toshkent vaqti)</i>")

            return "\n".join(lines)

        except Exception as e:
            logger.error("Failed to format price message: %s", e)
            return "❌ <b>Narxlarni olishda xatolik</b>"

    async def create_or_update_pinned_message(self) -> int:
        """Create or update the pinned price message in channel.

        Returns the message_id.
        """
        await self._load_message_id()

        try:
            coins = await self.get_configured_coins()
            text = await self.format_price_message(coins)

            if self.message_id:
                # Edit existing message
                await self.bot.edit_message_text(
                    chat_id=self.channel_id,
                    message_id=self.message_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                logger.info("Updated live price message (msg_id=%d)", self.message_id)
            else:
                # Create new message
                msg = await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                self.message_id = msg.message_id
                await self._save_message_id()
                logger.info("Created live price message (msg_id=%d)", self.message_id)

                # Pin the message
                await self.bot.pin_chat_message(
                    chat_id=self.channel_id,
                    message_id=self.message_id,
                    disable_notification=True,
                )
                logger.info("Pinned live price message")

        except Exception as e:
            logger.error("Failed to update pinned message: %s", e)
            self.message_id = None
            await self._save_message_id()
            raise

        return self.message_id

    async def run_loop(self) -> None:
        """Main loop: fetch prices and update pinned message."""
        interval = await self.get_update_interval()
        logger.info("Live price service started, updating every %ds", interval)

        while True:
            try:
                await self.create_or_update_pinned_message()
            except Exception as e:
                logger.error("Error in live price loop: %s", e)

            await asyncio.sleep(interval)


async def main():
    """Run live price service."""
    service = LivePriceService()
    await service.run_loop()


if __name__ == "__main__":
    asyncio.run(main())