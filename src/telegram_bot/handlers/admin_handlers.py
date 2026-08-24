"""Admin panel handlers — full admin management."""

import logging

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import (
    NewsRepository,
    RSSSourceRepository,
    SettingsRepository,
    DigestRepository,
    LogRepository,
)
# Lazy import to avoid circular dependency
# from src.crypto_prices.live import LivePriceService
from src.telegram_bot.filters.admin_filter import AdminFilter
from src.telegram_bot.kb.keyboards import (
    get_admin_main_keyboard,
    get_admin_news_keyboard,
    get_admin_sources_keyboard,
    get_source_detail_keyboard,
    get_admin_ai_keyboard,
    get_model_status_keyboard,
    get_admin_digest_keyboard,
    get_admin_system_keyboard,
    get_admin_live_prices_keyboard,
    get_back_keyboard,
    get_cancel_keyboard,
    get_pin_keyboard,
)
from src.telegram_bot.states import AdminStates, LivePriceStates

logger = logging.getLogger(__name__)

admin_router = Router()
admin_router.message.filter(AdminFilter())
admin_router.callback_query.filter(AdminFilter())

# In-memory set of authenticated admin user IDs (reset on bot restart)
_authenticated_admins: set[int] = set()


def _is_authenticated(user_id: int) -> bool:
    """Check if admin has entered the password this session."""
    if not settings.admin_password:
        return True  # No password configured = open access
    return user_id in _authenticated_admins


async def _telegraph_ready() -> bool:
    """Check whether a Telegraph access token is already stored."""
    from src.digest.schedule import KEY_TELEGRAPH_TOKEN
    try:
        async with get_session() as session:
            repo = SettingsRepository(session)
            return bool(await repo.get_value(KEY_TELEGRAPH_TOKEN))
    except Exception:
        return False


async def _require_auth(event: types.Message | types.CallbackQuery, state: FSMContext) -> bool:
    """Gate: if admin is not authenticated, show PIN pad for password.

    Returns True if authenticated (proceed), False if redirected to PIN input.
    """
    user_id = event.from_user.id
    if _is_authenticated(user_id):
        return True

    await state.clear()
    await state.set_state(AdminStates.waiting_for_admin_password)
    await state.update_data(pin_digits="")

    text = "🔒 <b>Admin Panel — Parol talab qilinadi</b>\n\n5 xonali PIN kodni kiriting:\n⬜ ⬜ ⬜ ⬜ ⬜"
    markup = get_pin_keyboard().as_markup()

    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup)
    return False


# ─── Entry points ──────────────────────────────────────────────

@admin_router.message(CommandStart())
async def admin_start(message: types.Message, state: FSMContext) -> None:
    """Admin /start — show admin panel (after auth check)."""
    if not await _require_auth(message, state):
        return
    await _show_admin_main(message)


@admin_router.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext) -> None:
    """Admin /admin — show admin panel (after auth check)."""
    if not await _require_auth(message, state):
        return
    await _show_admin_main(message)


async def _show_admin_main(message: types.Message) -> None:
    text = "⚙️ <b>Admin Panel</b>\n\nBoshqaruv bo'limini tanlang:"
    await message.answer(text, reply_markup=get_admin_main_keyboard().as_markup())


# ─── Main menu callbacks ───────────────────────────────────────

@admin_router.callback_query(F.data == "admin_main")
async def cb_admin_main(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not await _require_auth(callback, state):
        return
    text = "⚙️ <b>Admin Panel</b>\n\nBoshqaruv bo'limini tanlang:"
    await callback.message.edit_text(text, reply_markup=get_admin_main_keyboard().as_markup())
    await callback.answer()


# ─── PIN pad handlers ──────────────────────────────────────────

@admin_router.callback_query(F.data.regexp(r"^digit_\d$"), AdminStates.waiting_for_admin_password)
async def cb_pin_digit(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle PIN digit button press (digit_0 … digit_9)."""
    digit = callback.data.split("_")[1]
    data = await state.get_data()
    current = data.get("pin_digits", "")

    if len(current) >= 5:
        await callback.answer("⚠️ Faqat 5 xona!", show_alert=True)
        return

    current += digit
    await state.update_data(pin_digits=current)

    dots = " ".join("●" if i < len(current) else "⬜" for i in range(5))
    text = f"🔒 <b>Admin Panel — Parol talab qilinadi</b>\n\n5 xonali PIN kodni kiriting:\n{dots}"
    await callback.message.edit_text(text, reply_markup=get_pin_keyboard(current).as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "pin_clear", AdminStates.waiting_for_admin_password)
async def cb_pin_clear(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Clear all entered PIN digits."""
    await state.update_data(pin_digits="")
    text = "🔒 <b>Admin Panel — Parol talab qilinadi</b>\n\n5 xonali PIN kodni kiriting:\n⬜ ⬜ ⬜ ⬜ ⬜"
    await callback.message.edit_text(text, reply_markup=get_pin_keyboard().as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "pin_confirm", AdminStates.waiting_for_admin_password)
async def cb_pin_confirm(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm PIN — check against configured 5-digit admin password."""
    data = await state.get_data()
    entered = data.get("pin_digits", "")

    if len(entered) != 5:
        await callback.answer("⚠️ 5 xonali PIN kiriting!", show_alert=True)
        return

    if entered == settings.admin_password:
        _authenticated_admins.add(callback.from_user.id)
        await state.clear()
        await callback.message.edit_text("✅ Parol to'g'ri! Admin panel ochildi.")
        text = "⚙️ <b>Admin Panel</b>\n\nBoshqaruv bo'limini tanlang:"
        await callback.message.answer(text, reply_markup=get_admin_main_keyboard().as_markup())
        await callback.answer()
    else:
        await state.update_data(pin_digits="")
        dots = "⬜ ⬜ ⬜ ⬜ ⬜"
        text = f"❌ <b>Parol noto'g'ri!</b>\n\nQayta kiriting:\n{dots}"
        await callback.message.edit_text(text, reply_markup=get_pin_keyboard().as_markup())
        await callback.answer("❌ Noto'g'ri parol!", show_alert=True)


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


@admin_router.callback_query(F.data == "admin_delete_news")
async def cb_admin_delete_news(callback: types.CallbackQuery, session) -> None:
    """Show latest unpublished news for deletion."""
    news_repo = NewsRepository(session)
    pending = await news_repo.get_unpublished(limit=10)

    if not pending:
        text = "📭 O'chirish uchun yangilik yo'q."
    else:
        lines = ["🗑 <b>O'chirish uchun yangiliklar:</b>\n"]
        for n in pending:
            lines.append(f"📋 ID:{n.id} — {n.title[:60]}")
        lines.append("\n💬 O'chirish uchun yangilik ID raqamini yuboring (masalan: <code>delete 5</code>)")

    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_news").as_markup())
    await callback.answer()


@admin_router.message(F.text.regexp(r"^delete\s+(\d+)$"))
async def msg_delete_news_by_id(message: types.Message, session) -> None:
    """Delete a news item by ID (admin command: delete <id>)."""
    news_id = int(message.text.split()[1])
    news_repo = NewsRepository(session)
    deleted = await news_repo.delete(news_id)

    if deleted:
        await message.answer(f"✅ Yangilik (ID:{news_id}) o'chirildi!")
    else:
        await message.answer(f"❌ Yangilik (ID:{news_id}) topilmadi.")


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


@admin_router.callback_query(F.data == "admin_ai_models")
async def cb_admin_ai_models(callback: types.CallbackQuery) -> None:
    """Live-check every rotation model and list each one's status."""
    from src.ai_service.probe import probe_all

    await callback.answer("🔍 Barcha modellar tekshirilmoqda...")
    try:
        await callback.message.edit_text("⏳ Modellar tekshirilmoqda — bu 20-60 soniya olishi mumkin...")
    except Exception:
        pass

    try:
        results = await probe_all(settings.effective_model_list)
    except Exception as e:
        logger.error("Model probe failed: %s", e, exc_info=True)
        await callback.message.edit_text(
            f"❌ Tekshiruv xatosi: <code>{str(e)[:200]}</code>",
            reply_markup=get_model_status_keyboard().as_markup(),
        )
        return

    total = len(results)
    ok_count = sum(1 for ok, _ in results.values() if ok)
    unauth_count = sum(1 for ok, msg in results.values() if not ok and "401" in msg)

    provider = settings.effective_provider
    key_present = bool(
        settings.dashscope_api_key if provider == "dashscope"
        else settings.openrouter_api_key or settings.omniroute_api_key
    )
    key_label = "✅" if key_present else "❌ yo'q"

    lines = [
        "📊 <b>AI Modellar Holati</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🔧 Ishlayotgan: <b>{ok_count} / {total}</b>",
        f"📡 Provayder: <b>{provider}</b> | 🔑 Kalit: {key_label}",
    ]
    if unauth_count >= max(3, total // 4):
        key_name = "DASHSCOPE_API_KEY" if provider == "dashscope" else "OPENROUTER_API_KEY"
        lines.append(f"⚠️ <b>{unauth_count} ta model 401 qaytardi — {key_name} noto'g'ri/eskirgan!</b>")
    lines.append("")
    for model in settings.effective_model_list:
        ok, msg = results.get(model, (False, "Tekshirilmadi"))
        if ok:
            lines.append(f"  ✅ {model}")
        else:
            lines.append(f"  ❌ {model} — {msg}")

    header_len = len(lines[0]) + len(lines[1]) + len(lines[2]) + len(lines[3]) + 4
    chunks: list[str] = []
    current: list[str] = []
    size = header_len
    for line in lines:
        line_len = len(line) + 1
        if current and size + line_len > 3800:
            chunks.append("\n".join(current))
            current = [line]
            size = line_len
        else:
            current.append(line)
            size += line_len
    if current:
        chunks.append("\n".join(current))

    for i, chunk in enumerate(chunks):
        markup = get_model_status_keyboard().as_markup() if i == len(chunks) - 1 else None
        if i == 0:
            await callback.message.edit_text(chunk, reply_markup=markup)
        else:
            await callback.message.answer(chunk, reply_markup=markup)


@admin_router.callback_query(F.data == "admin_ai_provider")
async def cb_admin_ai_provider(callback: types.CallbackQuery) -> None:
    """Show current AI provider info."""
    api_key = settings.dashscope_api_key if settings.ai_provider == "dashscope" else settings.openrouter_api_key
    api_status = "✅ Mavjud" if api_key else "❌ Yo'q"
    text = (
        f"🔧 <b>AI Provayder</b>\n\n"
        f"📡 Joriy: <b>{settings.ai_provider}</b>\n"
        f"🔗 API Base: <code>{settings.dashscope_api_base if settings.ai_provider == 'dashscope' else settings.openrouter_api_base}</code>\n"
        f"🔑 API Key: <code>{api_status}</code>\n\n"
        f"ℹ️ Provayder .env faylidan o'zgartiriladi:\n"
        f"<code>AI_PROVIDER=dashscope</code> yoki <code>AI_PROVIDER=openrouter</code>"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_ai").as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_ai_model")
async def cb_admin_ai_model(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Show current model and prompt to change."""
    text = (
        f"🧠 <b>AI Model</b>\n\n"
        f"Joriy: <b>{settings.ai_model}</b>\n\n"
        f"Yangi model nomini yuboring:\n"
        f"DashScope: <code>qwen3.5-122b-a10b</code>, <code>qwen-plus</code>, <code>qwen-turbo</code>\n"
        f"OpenRouter: <code>free</code> (bepul modellar)"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard().as_markup())
    await state.set_state(AdminStates.waiting_for_ai_model)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_ai_model)
async def process_ai_model(message: types.Message, state: FSMContext) -> None:
    """Save new AI model to .env."""
    new_model = message.text.strip()
    import pathlib
    env_path = pathlib.Path(__file__).parent.parent.parent.parent / ".env"
    lines = env_path.read_text().splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("AI_MODEL="):
            lines[i] = f"AI_MODEL={new_model}"
            updated = True
            break
    if not updated:
        lines.append(f"AI_MODEL={new_model}")
    env_path.write_text("\n".join(lines) + "\n")
    await message.answer(f"✅ AI Model o'zgartirildi: <b>{new_model}</b>\n\n⚠️ Botni qayta ishga tushirish kerak!")
    await state.clear()


@admin_router.callback_query(F.data == "admin_ai_prompts")
async def cb_admin_ai_prompts(callback: types.CallbackQuery, session) -> None:
    """Show AI prompt information."""
    settings_repo = SettingsRepository(session)
    custom_prompt = await settings_repo.get_value("ai_analysis_prompt")
    from src.ai_service.prompt_loader import get_analysis_prompt
    current_prompt = get_analysis_prompt()

    translation_status = "✅ Yoqilgan" if settings.enable_translation else "❌ O'chirilgan"

    text = (
        "📝 <b>AI Promptlar</b>\n\n"
        f"📊 Tahlil prompti: {'✅ Maxsus' if custom_prompt else '⚡ Standart'}\n"
        f"🌍 Tarjima: {translation_status} ({settings.target_language})\n\n"
        "💬 Joriy prompt:\n<code>" + current_prompt[:300] + "</code>"
    )
    if custom_prompt:
        text += f"\n\n✅ Maxsus prompt DBda saqlangan"

    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_ai").as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "admin_ai_prompt_edit")
async def cb_admin_ai_prompt_edit(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt admin to enter a new AI analysis prompt."""
    from src.ai_service.prompt_loader import get_analysis_prompt
    current = get_analysis_prompt()

    text = (
        "✏️ <b>AI Prompt o'zgartirish</b>\n\n"
        "Yangi prompt matnini yuboring.\n\n"
        "⚠️ Promptda {title} va {content} o'rinlarini saqlang — ular yangilik sarlavha va tarkib bilan almashtiriladi.\n\n"
        "⚡ Joriy prompt:\n<code>" + current[:500] + "</code>"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard().as_markup())
    await state.set_state(AdminStates.waiting_for_prompt_edit)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_prompt_edit)
async def process_prompt_edit(message: types.Message, state: FSMContext, session) -> None:
    """Save custom AI prompt to DB and update runtime."""
    new_prompt = message.text.strip()

    if "{title}" not in new_prompt or "{content}" not in new_prompt:
        await message.answer(
            "❌ Promptda <code>{title}</code> va <code>{content}</code> o'rinlarini bo'lishi shart!\n\n"
            "Qayta yuboring yoki ❌ Bekor qilish tugmasini bosing."
        )
        return

    # Save to DB
    settings_repo = SettingsRepository(session)
    await settings_repo.set_value(
        "ai_analysis_prompt", new_prompt,
        value_type="string",
        description="Custom AI analysis prompt (overrides default)",
    )

    # Update runtime variable
    from src.ai_service.prompt_loader import set_analysis_prompt
    set_analysis_prompt(new_prompt)

    await message.answer(
        "✅ <b>AI Prompt o'zgartirildi!</b>\n\n"
        "💡 Yangi prompt darhol ishga tushadi — botni restart qilish shart emas.\n\n"
        "💬 Yangi prompt:\n<code>" + new_prompt[:300] + "</code>"
    )
    await state.clear()


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
    from src.digest import schedule as digest_schedule

    schedule_times = await digest_schedule.get_schedule_times()
    last_time = await digest_schedule.get_last_digest_time()

    text = (
        f"📅 <b>Digest Sozlamalari</b>\n\n"
        f"🕐 Jadvallar: <b>{', '.join(schedule_times)}</b>\n"
        f"🌍 Timezone: <b>{settings.digest_timezone}</b>\n"
        f"📤 Oxirgi digest: <b>{last_time.strftime('%d.%m.%Y %H:%M') if last_time else 'hali yuborilmagan'}</b>\n"
        f"📖 Telegraph: <b>{'✅ Sozlangan' if await _telegraph_ready() else '⏳ Birinchi yuborishda avtomatik yaratiladi'}</b>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_digest_keyboard().as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "digest_schedule_change")
async def cb_digest_schedule_change(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt admin to enter new digest schedule times."""
    from src.digest import schedule as digest_schedule

    current = await digest_schedule.get_schedule_times()
    text = (
        "🕐 <b>Digest jadvallarini o'zgartirish</b>\n\n"
        f"Joriy: <b>{', '.join(current)}</b>\n\n"
        "Yangi vaqtlarni HH:MM formatda, vergul bilan ajratib yuboring (kuniga bir nechta bo'lishi mumkin):\n"
        "Masalan: <code>08:00,12:00,18:00,22:00</code>\n\n"
        "⚠️ Jadvallar o'zgarishi bilan botni restart qilish SHART EMAS — darhol kuchga kiradi."
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard().as_markup())
    await state.set_state(AdminStates.waiting_for_digest_schedule)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_digest_schedule)
async def process_digest_schedule(message: types.Message, state: FSMContext) -> None:
    """Save new digest schedule and reschedule the job immediately."""
    from src.digest import schedule as digest_schedule
    from src.scheduler.scheduler import reschedule_digest_jobs

    try:
        times = await digest_schedule.set_schedule_times(message.text.strip())
    except ValueError as e:
        await message.answer(f"❌ {e}\n\nFormat: <code>08:00,12:00,18:00,22:00</code>")
        return

    applied = await reschedule_digest_jobs()
    if applied is None:
        extra = "\n\n⚠️ Jadvallar saqlandi — bot qayta ishga tushganda kuchga kiradi."
    else:
        extra = "\n\n✅ Jadvallar darhol yangilandi!"

    await message.answer(
        f"✅ <b>Digest jadvallari o'zgartirildi:</b> {', '.join(times)}{extra}"
    )
    await state.clear()


@admin_router.callback_query(F.data == "digest_send_now")
async def cb_digest_send_now(callback: types.CallbackQuery) -> None:
    """Trigger digest generation immediately."""
    await callback.answer("📅 Digest generatsiya boshlandi...", show_alert=True)

    try:
        from src.telegram_bot.publisher import Publisher
        from src.scheduler.jobs import generate_telegraph_digest
        bot = callback.bot
        publisher = Publisher(bot)
        await generate_telegraph_digest(publisher)
        await callback.message.answer("✅ <b>Digest yuborildi!</b>")
    except Exception as e:
        await callback.message.answer(f"❌ <b>Digest xato:</b> {e}")
        logger.error("Manual digest failed: %s", e)


@admin_router.callback_query(F.data == "admin_digest_test")
async def cb_admin_digest_test(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Manually trigger daily digest for testing — with auth check."""
    if not await _require_auth(callback, state):
        return

    await callback.answer("📰 Digest test boshlandi (dry-run, kanalga yuborilmaydi)...", show_alert=True)

    try:
        from src.telegram_bot.publisher import Publisher
        from src.scheduler.jobs import generate_telegraph_digest
        bot = callback.bot
        publisher = Publisher(bot)
        result = await generate_telegraph_digest(publisher, dry_run=True)
        if result.get("telegraph_url"):
            await callback.message.answer(
                f"✅ <b>Digest test muvaffaqiyatli (dry-run)!</b>\n\n"
                f"📰 Yangiliklar: {result.get('news_count', 0)}\n"
                f"📖 Sahifa: {result.get('telegraph_url')}\n\n"
                f"⚠️ Kanalga yuborilmadi — bu faqat sinov edi."
            )
        else:
            info = result.get("error") or "Sahifa yaratilmadi (yangilik yo'q bo'lishi mumkin)"
            await callback.message.answer(
                f"ℹ️ Digest test: {result.get('news_count', 0)} yangilik topildi\n{info}"
            )
    except Exception as e:
        await callback.message.answer(f"❌ <b>Digest test xato:</b> {e}")
        logger.error("Digest test failed: %s", e)


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


@admin_router.callback_query(F.data == "sys_redis")
async def cb_sys_redis(callback: types.CallbackQuery) -> None:
    """Show Redis connection status."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url)
        info = await r.info("server")
        ping = await r.ping()
        mem = await r.info("memory")
        await r.aclose()

        text = (
            f"📡 <b>Redis</b>\n\n"
            f"✅ Status: Connected\n"
            f"📋 Version: {info.get('redis_version', 'N/A')}\n"
            f"💾 Memory: {mem.get('used_memory_human', 'N/A')}\n"
            f"🔗 URL: <code>{settings.redis_url}</code>"
        )
    except Exception as e:
        text = (
            f"📡 <b>Redis</b>\n\n"
            f"❌ Status: Ulanish xatosi\n"
            f"⚠️ Xato: <code>{str(e)[:100]}</code>\n"
            f"🔗 URL: <code>{settings.redis_url}</code>\n\n"
            f"ℹ️ Redis mavjud bo'lmasa bot ishlayveradi, lekin Redis storage ishlamaydi."
        )

    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_system").as_markup())
    await callback.answer()


@admin_router.callback_query(F.data == "sys_metrics")
async def cb_sys_metrics(callback: types.CallbackQuery, session) -> None:
    """Show system metrics."""
    import psutil
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    text = (
        f"📊 <b>System Metrics</b>\n\n"
        f"💻 CPU: <b>{cpu}%</b>\n"
        f"💾 RAM: <b>{mem.percent}%</b> ({mem.available // 1024 // 1024} MB free)\n"
        f"📁 Disk: <b>{disk.percent}%</b> ({(disk.free // 1024 // 1024)} MB free)\n"
        f"⏱ Uptime: <b>{int(psutil.boot_time())}</b>"
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


# ─── Live Prices ───────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_live_prices")
async def cb_admin_live_prices(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Show live prices settings menu."""
    if not await _require_auth(callback, state):
        return
    text = "💰 <b>Live Narxlar Sozlamalari</b>\n\n"
    text += "Bu bo'limda kanalga qadalgan live crypto narxlarni boshqarasiz.\n\n"
    text += "Tangalar va yangilash intervalini o'zgartirishingiz mumkin."
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_live_prices_keyboard().as_markup(),
    )
    await callback.answer()


@admin_router.callback_query(F.data == "live_status")
async def cb_live_status(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Show current live prices status."""
    async with get_session() as session:
        repo = SettingsRepository(session)
        coins_str = await repo.get_value("live_price_coins")
        interval = await repo.get_int("live_price_interval", 60)

    coins = coins_str.split(",") if coins_str else ["bitcoin", "ethereum", "solana"]
    text = "📊 <b>Joriy holat</b>\n\n"
    text += f"🪙 Tangalar: {', '.join(coins)}\n"
    text += f"⏱ Interval: {interval} soniya\n"
    text += f"\n💡 Maslahat: Interval 15-300 soniya oralig'ida bo'lishi mumkin."
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_live_prices_keyboard().as_markup(),
    )
    await callback.answer()


@admin_router.callback_query(F.data == "live_coins_edit")
async def cb_live_coins_edit(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Edit the list of coins to display."""
    async with get_session() as session:
        repo = SettingsRepository(session)
        coins_str = await repo.get_value("live_price_coins")

    current_coins = coins_str or "bitcoin,ethereum,solana,binancecoin,ripple"
    text = "💊 <b>Tangalarni o'zgartirish</b>\n\n"
    text += "Hozirgi tangalar:\n"
    text += f"<code>{current_coins}</code>\n\n"
    text += "Yangi tangalar ro'yxatini vergul bilan ajratib yuboring:\n"
    text += "Misol: <code>bitcoin,ethereum,solana,cardano,polkadot</code>\n\n"
    text += "CoinGecko coin ID laridan foydalaning."
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard().as_markup())
    await state.set_state(LivePriceStates.editing_coins)
    await callback.answer()


@admin_router.message(LivePriceStates.editing_coins)
async def process_coins_edit(message: types.Message, state: FSMContext, session) -> None:
    """Save new coins list."""
    coins_text = message.text.strip()
    coins = [c.strip() for c in coins_text.split(",") if c.strip()]

    if not coins:
        await message.answer("❌ Xato: Bo'sh ro'yxat! Qayta kiriting:")
        return

    async with get_session() as session:
        repo = SettingsRepository(session)
        await repo.set_value(
            "live_price_coins",
            ",".join(coins),
            description="Live prices uchun coin ID lar (vergul bilan)",
        )

    await state.clear()
    await message.answer(
        f"✅ Tangalar saqlandi: {', '.join(coins)}\n\nNarxlar keyingi yangilanishda ko'rinadi.",
        reply_markup=get_admin_live_prices_keyboard().as_markup(),
    )


@admin_router.callback_query(F.data == "live_interval_edit")
async def cb_live_interval_edit(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Edit the update interval."""
    async with get_session() as session:
        repo = SettingsRepository(session)
        interval = await repo.get_int("live_price_interval", 60)

    text = "⏱ <b>Intervalni o'zgartirish</b>\n\n"
    text += f"Hozirgi interval: <b>{interval} soniya</b>\n\n"
    text += "Yangi intervalni soniyalarda kiriting (15-300):\n"
    text += "Masalan: <code>30</code>, <code>60</code>, <code>120</code>"
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard().as_markup())
    await state.set_state(LivePriceStates.editing_interval)
    await callback.answer()


@admin_router.message(LivePriceStates.editing_interval)
async def process_interval_edit(message: types.Message, state: FSMContext, session) -> None:
    """Save new interval."""
    try:
        interval = int(message.text.strip())
        if interval < 15 or interval > 300:
            await message.answer("❌ Xato: Interval 15-300 soniya oralig'ida bo'lishi kerak! Qayta kiriting:")
            return
    except ValueError:
        await message.answer("❌ Xato: Faqat raqam kiriting! Qayta kiriting:")
        return

    async with get_session() as session:
        repo = SettingsRepository(session)
        await repo.set_value(
            "live_price_interval",
            str(interval),
            value_type="int",
            description="Live prices yangilash intervali (soniya)",
        )

    await state.clear()
    await message.answer(
        f"✅ Interval saqlandi: har {interval} soniyada\n\nBot qayta ishga tushirilgandan keyin kuchga kiradi.",
        reply_markup=get_admin_live_prices_keyboard().as_markup(),
    )


@admin_router.callback_query(F.data == "live_refresh_now")
async def cb_live_refresh_now(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Manually refresh live prices now."""
    if not await _require_auth(callback, state):
        return
    try:
        from src.scheduler.jobs import get_live_price_service
        live_service = get_live_price_service()
        await live_service.create_or_update_pinned_message()
        await callback.answer("✅ Narxlar yangilandi!", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Xatolik: {e}", show_alert=True)


@admin_router.callback_query(F.data == "live_reset_pinned")
async def cb_live_reset_pinned(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Delete the tracked live price message and create a fresh pinned one."""
    if not await _require_auth(callback, state):
        return
    try:
        from src.scheduler.jobs import get_live_price_service
        live_service = get_live_price_service()
        await live_service.reset_pinned_message()
        await callback.answer("✅ Eski xabar o'chirildi va yangi live narx xabari yaratildi!", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Xatolik: {e}", show_alert=True)
