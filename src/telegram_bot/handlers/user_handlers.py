"""User-facing handlers — /start, /help, news, stats."""

import logging

from aiogram import Router, types
from aiogram.filters import Command

from src.core.config import settings
from src.core.repositories import NewsRepository, UserRepository

logger = logging.getLogger(__name__)

user_router = Router()


@user_router.message(Command("start"))
async def cmd_start(message: types.Message, session) -> None:
    """Handle /start — register user and show welcome message."""
    user_repo = UserRepository(session)
    user = await user_repo.get_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    from src.telegram_bot.kb.keyboards import get_user_start_keyboard

    text = (
        f"👋 Salom, <b>{message.from_user.first_name or 'foydalanuvchi'}</b>!\n\n"
        f"📰 <b>Kripto Yangiliklar Bot</b>ga xush kelibsiz!\n\n"
        f"Men sizga kriptovalyuta bozori haqida eng so'nggi va muhim "
        f"yangiliklarni yetkazib beraman.\n\n"
        f"🤖 AI yordamida tahlil qilingan yangiliklar har bir soatda yangilanadi."
    )
    await message.answer(text, reply_markup=get_user_start_keyboard().as_markup())


@user_router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Handle /help — show help text."""
    text = (
        "📰 <b>Kripto Yangiliklar Bot — Yordam</b>\n\n"
        "🔹 /start — Botni ishga tushirish\n"
        "🔹 /news — So'nggi yangiliklar\n"
        "🔹 /stats — Statistika\n"
        "🔹 /help — Yordam\n\n"
        "Yangiliklar AI orqali tahlil qilinadi va faqat muhim "
        "yangiliklar e'lon qilinadi.\n\n"
        f"⚙️ Admin: @{(await message.bot.get_me()).username}"
    )
    await message.answer(text)


@user_router.message(Command("news"))
async def cmd_news(message: types.Message, session) -> None:
    """Handle /news — show latest news."""
    news_repo = NewsRepository(session)
    recent = await news_repo.get_recent(hours=24, limit=5)

    if not recent:
        await message.answer("📭 Hozircha yangiliklar yo'q. Keyinroq tekshiring!")
        return

    lines = ["📰 <b>So'nggi yangiliklar:</b>\n"]
    for i, n in enumerate(recent, 1):
        emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(n.sentiment, "⚪")
        lines.append(f"{emoji} <b>{i}.</b> {n.title}")
        if n.summary:
            lines.append(f"   <i>{n.summary[:100]}</i>")
        lines.append("")

    await message.answer("\n".join(lines))


@user_router.message(Command("stats"))
async def cmd_stats(message: types.Message, session) -> None:
    """Handle /stats — show bot statistics."""
    news_repo = NewsRepository(session)
    user_repo = UserRepository(session)

    stats = await news_repo.get_stats_summary()
    user_count = await user_repo.count()

    text = (
        "📊 <b>Bot Statistikasi</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{user_count}</b>\n"
        f"📰 Jami yangiliklar: <b>{stats['total']}</b>\n"
        f"📅 Bugun: <b>{stats['today']}</b>\n"
        f"📤 E'lon qilingan: <b>{stats['published']}</b>\n"
        f"📊 O'rtacha muhimlik: <b>{stats['avg_importance']}</b>/100"
    )
    await message.answer(text)


@user_router.callback_query(lambda c: c.data == "user_news")
async def cb_user_news(callback: types.CallbackQuery, session) -> None:
    """Handle user 'Yangiliklar' button."""
    news_repo = NewsRepository(session)
    recent = await news_repo.get_recent(hours=24, limit=5)

    if not recent:
        await callback.answer("📭 Yangiliklar yo'q", show_alert=True)
        return

    lines = ["📰 <b>So'nggi yangiliklar:</b>\n"]
    for i, n in enumerate(recent, 1):
        emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(n.sentiment, "⚪")
        lines.append(f"{emoji} <b>{i}.</b> {n.title}")
        if n.summary:
            lines.append(f"   <i>{n.summary[:100]}</i>")
        lines.append("")

    await callback.message.answer("\n".join(lines))
    await callback.answer()


@user_router.callback_query(lambda c: c.data == "user_stats")
async def cb_user_stats(callback: types.CallbackQuery, session) -> None:
    """Handle user 'Statistika' button."""
    news_repo = NewsRepository(session)
    user_repo = UserRepository(session)

    stats = await news_repo.get_stats_summary()
    user_count = await user_repo.count()

    text = (
        "📊 <b>Bot Statistikasi</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{user_count}</b>\n"
        f"📰 Jami yangiliklar: <b>{stats['total']}</b>\n"
        f"📅 Bugun: <b>{stats['today']}</b>\n"
        f"📤 E'lon qilingan: <b>{stats['published']}</b>\n"
        f"📊 O'rtacha muhimlik: <b>{stats['avg_importance']}</b>/100"
    )
    await callback.message.answer(text)
    await callback.answer()


@user_router.callback_query(lambda c: c.data == "user_help")
async def cb_user_help(callback: types.CallbackQuery) -> None:
    """Handle user 'Yordam' button."""
    text = (
        "📰 <b>Kripto Yangiliklar Bot</b>\n\n"
        "🔹 Yangiliklar har soatda yangilanadi\n"
        "🔹 AI orqali tahlil qilinadi\n"
        "🔹 Faqat muhim yangiliklar e'lon qilinadi\n"
        "🔹 O'zbek tilida xulosa beriladi"
    )
    await callback.message.answer(text)
    await callback.answer()
