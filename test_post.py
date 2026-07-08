"""Send a test post to the Telegram channel."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.core.config import settings


async def main() -> None:
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    text = (
        "🟢 <b>Test xabar</b>\n\n"
        "Bu — Crypto News AI Bot imzosi testi.\n\n"
        "💡 <i>AI tahlil namunasi: yangilik bozorga ijobiy ta'sir qilishi mumkin.</i>\n\n"
        "🔗 <a href='https://example.com'>Manba</a>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 @{settings.telegram_channel_username}"
    )

    await bot.send_message(
        chat_id=settings.telegram_channel_id,
        text=text,
        disable_web_page_preview=True,
    )
    await bot.session.close()
    print("Test post yuborildi.")


if __name__ == "__main__":
    asyncio.run(main())
