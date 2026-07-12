"""Crypto price fetcher job — runs periodically to update pinned message."""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram.exceptions import TelegramAPIError

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import SettingsRepository
from src.crypto_prices.service import CryptoPriceService
from src.telegram_bot.bot import Bot

logger = logging.getLogger(__name__)


class LivePriceService:
    """Manages live crypto price display in channel.

    Implemented as a singleton so the scheduler and admin handlers share the
    same in-memory state and never create duplicate pinned messages.
    """

    _instance: "LivePriceService | None" = None
    _lock: asyncio.Lock | None = None

    def __new__(cls) -> "LivePriceService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._lock = asyncio.Lock()
        return cls._instance

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
            if mid and mid.isdigit():
                self.message_id = int(mid)
            else:
                self.message_id = None

    async def _save_message_id(self) -> None:
        """Persist current message_id to DB."""
        async with get_session() as session:
            repo = SettingsRepository(session)
            value = str(self.message_id) if self.message_id is not None else ""
            await repo.set_value("live_price_message_id", value)

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
                    lines.append(f"{name}{price}  {change}")
                else:
                    lines.append(f"{coin_id}  ---  ---")

            lines.append("")
            lines.append(f"🕐 Yangilangan: {now.strftime('%H:%M:%S')} (Toshkent vaqti)")

            return "\n".join(lines)

        except Exception as e:
            logger.error("Failed to format price message: %s", e)
            return "❌ Narxlarni olishda xatolik"

    async def _try_delete_message(self, message_id: int) -> bool:
        """Try to delete a channel message by ID. Return True if successful."""
        try:
            await self.bot.delete_message(chat_id=self.channel_id, message_id=message_id)
            return True
        except TelegramAPIError as e:
            logger.debug("Could not delete message (msg_id=%d): %s", message_id, e)
            return False

    async def create_or_update_pinned_message(self) -> int:
        """Create or update the pinned price message in channel.

        If the pinned message was deleted, creates a new one immediately.
        Returns the message_id.
        """
        if self._lock is None:
            # Defensive: __new__ always initializes the lock, but keep type checker happy
            raise RuntimeError("LivePriceService lock is not initialized")

        async with self._lock:
            await self._load_message_id()

            coins = await self.get_configured_coins()
            text = await self.format_price_message(coins)

            if self.message_id:
                try:
                    await self.bot.edit_message_text(
                        chat_id=self.channel_id,
                        message_id=self.message_id,
                        text=text,
                        disable_web_page_preview=True,
                    )
                    logger.info("Updated live price message (msg_id=%d)", self.message_id)
                    return self.message_id
                except TelegramAPIError as e:
                    error_msg = str(e).lower()
                    # Message was deleted or otherwise unavailable — need a new one.
                    if any(
                        phrase in error_msg
                        for phrase in (
                            "message to edit not found",
                            "message_id_invalid",
                            "message can't be edited",
                            "message is not modified",
                        )
                    ):
                        logger.warning(
                            "Live price message (msg_id=%d) unavailable: %s — re-creating",
                            self.message_id, e,
                        )
                    else:
                        logger.error(
                            "Failed to edit live price message (msg_id=%d): %s",
                            self.message_id, e,
                        )
                        # Don't create a duplicate for transient errors.
                        return self.message_id

                # Old message is gone; try to remove it (best effort) and create a new one.
                old_message_id = self.message_id
                self.message_id = None
                await self._save_message_id()
                await self._try_delete_message(old_message_id)

            msg = await self.bot.send_message(
                chat_id=self.channel_id,
                text=text,
                disable_web_page_preview=True,
            )
            self.message_id = msg.message_id
            await self._save_message_id()
            logger.info("Created live price message (msg_id=%d)", self.message_id)

            try:
                await self.bot.pin_chat_message(
                    chat_id=self.channel_id,
                    message_id=self.message_id,
                    disable_notification=True,
                )
                logger.info("Pinned live price message")
            except TelegramAPIError as e:
                logger.warning("Could not pin live price message: %s", e)

            return self.message_id

    async def reset_pinned_message(self) -> int:
        """Delete the currently tracked message and create a fresh one.

        Useful when there are duplicate live price messages in the channel and
        the admin wants to start clean.
        """
        if self._lock is None:
            raise RuntimeError("LivePriceService lock is not initialized")

        async with self._lock:
            await self._load_message_id()
            if self.message_id:
                await self._try_delete_message(self.message_id)
                self.message_id = None
                await self._save_message_id()

        return await self.create_or_update_pinned_message()

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
