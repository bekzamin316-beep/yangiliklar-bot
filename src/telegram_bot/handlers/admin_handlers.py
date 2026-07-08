"""Admin panel handlers — full admin management."""

import logging

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from src.core.config import settings
from src.core.repositories import (
    NewsRepository,
    RSSSourceRepository,
    SettingsRepository,
    DigestRepository,
    LogRepository,
)
from src.telegram_bot.filters.admin_filter import AdminFilter
from src.telegram_bot.kb.keyboards import (
    get_admin_main_keyboard,
    get_admin_news_keyboard,
    get_admin_sources_keyboard,
    get_source_detail_keyboard,
    get_admin_ai_keyboard,
    get_admin_digest_keyboard,
    get_admin_system_keyboard,
    get_back_keyboard,
    get_cancel_keyboard,
)
from src.telegram_bot.states import AdminStates

logger = logging.getLogger(__name__)

admin_router = Router()
admin_router.message.filter(AdminFilter())
admin_router.callback_query.filter(AdminFilter())


# ─── Entry points ──────────────────────────────────────────────

@admin_router.message(CommandStart())
async def admin_start(message: types.Message) -> None:
    """Admin /start — show admin panel."""
    await _show_admin_main(message)


@admin_router.message(Command("admin"))
async def admin_panel(message: types.Message) -> None:
    """Admin /admin — show admin panel."""
    await _show_admin_main(message)


async def _show_admin_main(message: types.Message) -> None:
    text = "⚙️ <b>Admin Panel</b>\n\nBoshqaruv bo'limini tanlang:"
    await message.answer(text, reply_markup=get_admin_main_keyboard().as_markup())


# ─── Main menu callbacks ───────────────────────────────────────

@admin_router.callback_query(F.data == "admin_main")
async def cb_admin_main(callback: types.CallbackQuery) -> None:
    text = "⚙️ <b>Admin Panel</b>\n\nBoshqaruv bo'limini tanlang:"
    await callback.message.edit_text(text, reply_markup=get_admin_main_keyboard().as_markup())
    await callback.answer()


# ─── Statistics ────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: types.CallbackQuery, session) -> None:
    news_repo = NewsRepository(session)
    stats = await news_repo.get_stats_summary()

    text = (
        "📊 <b>Statistika</b>\n\n"
        f"📰 Jami yangiliklar: <b>{stats['total']}</b>\n"
        f"📅 Bugun: <b>{stats['today']}</b>\n"
        f"📤 E'lon qilingan: <b>{stats['published']}</b>\n"
        f"📊 O'rtacha muhimlik: <b>{stats['avg_importance']}</b>/100"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard().as_markup())
    await callback.answer()


# ─── News management ───────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_news")
async def cb_admin_news(callback: types.CallbackQuery) -> None:
    text = "📰 <b>Yangiliklar boshqaruvi</b>"
    await callback.message.edit_text(text, reply_markup=get_admin_news_keyboard().as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_pending_news")
async def cb_admin_pending(callback: types.CallbackQuery, session) -> None:
    news_repo = NewsRepository(session)
    pending = await news_repo.get_unpublished(limit=10)

    if not pending:
        text = "📭 Kutilayotgan yangiliklar yo'q."
    else:
        lines = [f"📋 <b>Kutilayotgan yangiliklar ({len(pending)}):</b>\n"]
        for i, n in enumerate(pending, 1):
            emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(n.sentiment, "⚪")
            lines.append(f"{emoji} {i}. {n.title[:60]} (score: {n.importance_score})")
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_news").as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_publish_now")
async def cb_admin_publish_now(callback: types.CallbackQuery, session) -> None:
    """Manually trigger publishing of pending news."""
    news_repo = NewsRepository(session)
    pending = await news_repo.get_unpublished(limit=5)

    if not pending:
        await callback.answer("📭 E'lon qilish uchun yangilik yo'q", show_alert=True)
        return

    # Mark as published (actual publishing is done by scheduler/publisher)
    count = 0
    for n in pending:
        await news_repo.update(n.id, is_published=True)
        count += 1

    await callback.answer(f"✅ {count} ta yangilik e'lon qilindi", show_alert=True)


# ─── RSS Sources ───────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_sources")
async def cb_admin_sources(callback: types.CallbackQuery, session) -> None:
    rss_repo = RSSSourceRepository(session)
    sources = await rss_repo.get_active_sources()

    text = "🔗 <b>RSS Manbalar</b>\n\n"
    if sources:
        for s in sources:
            status = "✅" if s.is_active else "❌"
            text += f"{status} {s.name}\n"
            text += f"   📊 Fetches: {s.fetch_count} | Errors: {s.error_count}\n\n"
    else:
        text += "📭 Manbalar yo'q. .env dan qo'shiladi."

    await callback.message.edit_text(text, reply_markup=get_admin_sources_keyboard(sources).as_markup())
    await callback.answer()


@admin_router.callback_query(F.data.startswith("source_"))
async def cb_source_detail(callback: types.CallbackQuery, session) -> None:
    source_id = int(callback.data.split("_")[1])
    rss_repo = RSSSourceRepository(session)
    source = await rss_repo.get_by_id(source_id)

    if not source:
        await callback.answer("❌ Manba topilmadi", show_alert=True)
        return

    status = "✅ Faol" if source.is_active else "❌ O'chirilgan"
    text = (
        f"🔗 <b>{source.name}</b>\n\n"
        f"📎 URL: <code>{source.url}</code>\n"
        f"📊 Status: {status}\n"
        f"📥 Fetches: {source.fetch_count}\n"
        f"❌ Errors: {source.error_count}\n"
    )
    if source.last_error:
        text += f"⚠️ Oxirgi xato: {source.last_error[:100]}\n"

    await callback.message.edit_text(text, reply_markup=get_source_detail_keyboard(source_id, source.is_active).as_markup())
    await callback.answer()


@admin_router.callback_query(F.data.startswith("toggle_source_"))
async def cb_toggle_source(callback: types.CallbackQuery, session) -> None:
    source_id = int(callback.data.split("_")[2])
    rss_repo = RSSSourceRepository(session)
    source = await rss_repo.get_by_id(source_id)

    if source:
        await rss_repo.update(source_id, is_active=not source.is_active)
        status = "yoqildi ✅" if not source.is_active else "o'chirildi ❌"
        await callback.answer(f"Manba {status}", show_alert=True)
    else:
        await callback.answer("❌ Manba topilmadi", show_alert=True)


@admin_router.callback_query(F.data.startswith("delete_source_"))
async def cb_delete_source(callback: types.CallbackQuery, session) -> None:
    source_id = int(callback.data.split("_")[2])
    rss_repo = RSSSourceRepository(session)
    await rss_repo.delete(source_id)
    await callback.answer("🗑 Manba o'chirildi", show_alert=True)
    # Refresh sources list
    sources = await rss_repo.get_active_sources()
    text = "🔗 <b>RSS Manbalar</b>\n\n"
    for s in sources:
        status = "✅" if s.is_active else "❌"
        text += f"{status} {s.name}\n"
    await callback.message.edit_text(text, reply_markup=get_admin_sources_keyboard(sources).as_markup())


@admin_router.callback_query(F.data == "rss_add")
async def cb_rss_add(callback: types.CallbackQuery, state: FSMContext) -> None:
    text = "➕ <b>Yangi RSS manba qo'shish</b>\n\nRSS feed URL ni yuboring:"
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard().as_markup())
    await state.set_state(AdminStates.waiting_for_rss_url)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_rss_url)
async def process_rss_url(message: types.Message, state: FSMContext, session) -> None:
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer("❌ Noto'g'ri URL. http:// yoki https:// bilan boshlanishi kerak.")
        return

    rss_repo = RSSSourceRepository(session)
    existing = await rss_repo.get_by_url(url)
    if existing:
        await message.answer("❌ Bu URL allaqachon mavjud!")
        await state.clear()
        return

    # Derive name from URL
    name = url.split("//")[-1].split("/")[0]
    await rss_repo.create(name=name, url=url, is_active=True)

    await message.answer(f"✅ <b>{name}</b> manba qo'shildi!")
    await state.clear()


@admin_router.callback_query(F.data == "rss_refresh")
async def cb_rss_refresh(callback: types.CallbackQuery, session) -> None:
    """Re-seed RSS sources from .env."""
    rss_repo = RSSSourceRepository(session)
    await rss_repo.seed_sources(settings.rss_source_list)
    sources = await rss_repo.get_active_sources()

    text = "🔗 <b>RSS Manbalar</b> (yangilandi)\n\n"
    for s in sources:
        status = "✅" if s.is_active else "❌"
        text += f"{status} {s.name}\n"

    await callback.message.edit_text(text, reply_markup=get_admin_sources_keyboard(sources).as_markup())
    await callback.answer("✅ Yangilandi", show_alert=True)


# ─── AI Settings ───────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_ai")
async def cb_admin_ai(callback: types.CallbackQuery) -> None:
    text = (
        f"🤖 <b>AI Sozlamalar</b>\n\n"
        f"📡 Provayder: <b>{settings.ai_provider}</b>\n"
        f"🧠 Model: <b>{settings.ai_model}</b>\n"
        f"📊 Muhimlik chegarasi: <b>{settings.importance_threshold}</b>/100"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_ai_keyboard().as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_ai_test")
async def cb_admin_ai_test(callback: types.CallbackQuery) -> None:
    """Test AI provider with a simple prompt."""
    await callback.answer("🧪 AI test qilinmoqda...", show_alert=True)

    try:
        from src.ai_service.service import AIService
        ai = AIService()
        from src.ai_service.models import NewsAnalysis
        result = await ai.analyze_news(
            "Bitcoin reaches new all-time high",
            "Bitcoin price surged past $100,000 for the first time."
        )
        text = (
            f"✅ <b>AI Test muvaffaqiyatli!</b>\n\n"
            f"📝 Xulosa: {result.summary_uz}\n"
            f"💡 Tahlil: {result.analysis_uz}\n"
            f"📊 Muhimlik: {result.importance_score}\n"
            f"🎯 Sentiment: {result.sentiment}"
        )
    except Exception as e:
        text = f"❌ <b>AI Test xato:</b>\n\n<code>{e}</code>"

    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_ai").as_markup())


# ─── Digest ────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_digest")
async def cb_admin_digest(callback: types.CallbackQuery) -> None:
    text = (
        f"📅 <b>Digest Sozlamalari</b>\n\n"
        f"🕐 Vaqt: <b>{settings.digest_hour:02d}:{settings.digest_minute:02d}</b>\n"
        f"🌍 Timezone: <b>{settings.digest_timezone}</b>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_digest_keyboard().as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "digest_history")
async def cb_digest_history(callback: types.CallbackQuery, session) -> None:
    digest_repo = DigestRepository(session)
    digests = await digest_repo.get_recent(limit=5)

    if not digests:
        text = "📭 Digest tarixi bo'sh."
    else:
        lines = ["📋 <b>Oxirgi digestlar:</b>\n"]
        for d in digests:
            lines.append(f"📅 {d.digest_date} — {d.news_count} ta yangilik")
            if d.ai_summary:
                lines.append(f"   <i>{d.ai_summary[:80]}</i>")
            lines.append("")
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_digest").as_markup())
    await callback.answer()


# ─── System ────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_system")
async def cb_admin_system(callback: types.CallbackQuery) -> None:
    text = "⚙️ <b>Tizim Monitoring</b>"
    await callback.message.edit_text(text, reply_markup=get_admin_system_keyboard().as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "sys_db")
async def cb_sys_db(callback: types.CallbackQuery, session) -> None:
    news_repo = NewsRepository(session)
    rss_repo = RSSSourceRepository(session)
    news_count = await news_repo.count()
    rss_count = await rss_repo.count()

    text = (
        f"🗄 <b>Database</b>\n\n"
        f"📰 Yangiliklar: {news_count}\n"
        f"🔗 RSS manbalar: {rss_count}\n"
        f"📡 DB turi: {settings.db_type}"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_system").as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "sys_rss")
async def cb_sys_rss(callback: types.CallbackQuery, session) -> None:
    rss_repo = RSSSourceRepository(session)
    sources = await rss_repo.get_active_sources()
    total_fetches = sum(s.fetch_count for s in sources)
    total_errors = sum(s.error_count for s in sources)

    text = (
        f"📰 <b>RSS Tizimi</b>\n\n"
        f"🔗 Faol manbalar: {len(sources)}\n"
        f"📥 Jami fetches: {total_fetches}\n"
        f"❌ Jami xatolar: {total_errors}\n"
        f"⏱ Tekshiruv intervali: {settings.news_check_interval}s"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_system").as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "sys_ai")
async def cb_sys_ai(callback: types.CallbackQuery) -> None:
    text = (
        f"🤖 <b>AI Tizimi</b>\n\n"
        f"📡 Provayder: {settings.ai_provider}\n"
        f"🧠 Model: {settings.ai_model}\n"
        f"📊 Muhimlik chegarasi: {settings.importance_threshold}\n"
        f"⏱ Timeout: {settings.request_timeout}s"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_system").as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_logs")
async def cb_admin_logs(callback: types.CallbackQuery, session) -> None:
    log_repo = LogRepository(session)
    logs = await log_repo.get_recent(limit=10)

    if not logs:
        text = "📭 Loglar bo'sh."
    else:
        lines = ["📋 <b>Oxirgi loglar:</b>\n"]
        for log in logs:
            lines.append(f"[{log.level}] {log.module}: {log.message[:60]}")
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=get_back_keyboard().as_markup())
    await callback.answer()


# ─── Channel Post ──────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_channel_post")
async def cb_channel_post(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start channel post FSM — admin can send text, photo, or video."""
    text = (
        "📢 <b>Kanalga xabar yuborish</b>\n\n"
        "Kanalga yuboriladigan xabar matnini, rasmni yoki videoni yuboring.\n\n"
        "📝 Matn yuborsang — chiroyli formatda kanalga chiqadi\n"
        "🖼 Rasm yuborsang — rasm + sarlavha kanalga chiqadi\n"
        "🎬 Video yuborsang — video + sarlavha kanalga chiqadi\n\n"
        "⚠️ Xabar kanalga <b>darhol</b> yuboriladi!"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard().as_markup())
    await state.set_state(AdminStates.waiting_for_channel_post)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_channel_post, F.text)
async def process_channel_text(message: types.Message, state: FSMContext) -> None:
    """Publish text post to channel."""
    from src.telegram_bot.publisher import Publisher
    bot = message.bot
    publisher = Publisher(bot)

    raw_text = message.text.strip()
    formatted = _format_channel_post(raw_text)

    try:
        msg = await bot.send_message(
            chat_id=publisher.channel_id,
            text=formatted,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        await message.answer(
            f"✅ <b>Kanalga yuborildi!</b>\n\n"
            f"📋 Message ID: {msg.message_id}\n"
            f"📢 https://t.me/{settings.telegram_channel_username}/{msg.message_id}",
        )
        logger.info("Admin published text to channel (msg_id=%d)", msg.message_id)
    except Exception as e:
        await message.answer(f"❌ <b>Xatolik:</b> {e}")
        logger.error("Failed to publish text to channel: %s", e)

    await state.clear()


@admin_router.message(AdminStates.waiting_for_channel_post, F.photo)
async def process_channel_photo(message: types.Message, state: FSMContext) -> None:
    """Publish photo post to channel."""
    from src.telegram_bot.publisher import Publisher
    bot = message.bot
    publisher = Publisher(bot)

    photo = message.photo[-1]  # highest resolution
    caption = message.caption or ""
    formatted_caption = _format_channel_post(caption)

    # Telegram caption limit is 1024 chars
    if len(formatted_caption) > 1024:
        formatted_caption = formatted_caption[:1020] + "..."

    try:
        msg = await bot.send_photo(
            chat_id=publisher.channel_id,
            photo=photo.file_id,
            caption=formatted_caption,
            parse_mode=ParseMode.HTML,
        )
        await message.answer(
            f"✅ <b>Rasm kanalga yuborildi!</b>\n\n"
            f"📋 Message ID: {msg.message_id}\n"
            f"📢 https://t.me/{settings.telegram_channel_username}/{msg.message_id}",
        )
        logger.info("Admin published photo to channel (msg_id=%d)", msg.message_id)
    except Exception as e:
        await message.answer(f"❌ <b>Xatolik:</b> {e}")
        logger.error("Failed to publish photo to channel: %s", e)

    await state.clear()


@admin_router.message(AdminStates.waiting_for_channel_post, F.video)
async def process_channel_video(message: types.Message, state: FSMContext) -> None:
    """Publish video post to channel."""
    from src.telegram_bot.publisher import Publisher
    bot = message.bot
    publisher = Publisher(bot)

    video = message.video
    caption = message.caption or ""
    formatted_caption = _format_channel_post(caption)

    # Telegram caption limit is 1024 chars
    if len(formatted_caption) > 1024:
        formatted_caption = formatted_caption[:1020] + "..."

    try:
        msg = await bot.send_video(
            chat_id=publisher.channel_id,
            video=video.file_id,
            caption=formatted_caption,
            parse_mode=ParseMode.HTML,
        )
        await message.answer(
            f"✅ <b>Video kanalga yuborildi!</b>\n\n"
            f"📋 Message ID: {msg.message_id}\n"
            f"📢 https://t.me/{settings.telegram_channel_username}/{msg.message_id}",
        )
        logger.info("Admin published video to channel (msg_id=%d)", msg.message_id)
    except Exception as e:
        await message.answer(f"❌ <b>Xatolik:</b> {e}")
        logger.error("Failed to publish video to channel: %s", e)

    await state.clear()


def _format_channel_post(text: str) -> str:
    """Format a channel post with signature footer."""
    lines = [text]

    if settings.telegram_channel_username:
        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━━\n📢 https://t.me/{settings.telegram_channel_username}")

    return "\n".join(lines)


# ─── Cancel ────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "cancel_action")
async def cb_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Admin Panel</b>\n\nBoshqaruv bo'limini tanlang:",
        reply_markup=get_admin_main_keyboard().as_markup(),
    )
    await callback.answer("❌ Bekor qilindi")
