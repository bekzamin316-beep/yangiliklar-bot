"""Admin handlers for Telegram bot."""

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from app.telegram.filters.admin_filter import AdminFilter
from app.telegram.keyboards import (
    get_main_admin_keyboard,
    get_ai_settings_keyboard,
    get_prompt_management_keyboard,
    get_source_management_keyboard,
    get_digest_settings_keyboard,
    get_system_settings_keyboard,
)
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

admin_router = Router()
admin_router.message.filter(AdminFilter())
admin_router.callback_query.filter(AdminFilter())


@admin_router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command."""
    await message.answer(
        f"👋 Assalomu alaykum, {message.from_user.first_name}!\n\n"
        "🤖 Bu Crypto News AI Bot admin paneli.\n"
        "Quyidagi tugmalardan birini tanlang:",
        reply_markup=get_main_admin_keyboard()
    )


@admin_router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Handle /admin command."""
    await message.answer(
        "⚙️ Admin Panel",
        reply_markup=get_main_admin_keyboard()
    )


@admin_router.callback_query(F.data == "admin_main")
async def admin_main(callback: types.CallbackQuery):
    """Show main admin menu."""
    await callback.message.edit_text(
        "⚙️ Admin Panel",
        reply_markup=get_main_admin_keyboard()
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery, db_session: AsyncSession):
    """Show statistics."""
    # TODO: Implement statistics fetching from database
    stats_text = (
        "📊 **Statistika**\n\n"
        "📰 E'lon qilingan yangiliklar: 0\n"
        "⏭️ E'tiborga olinmagan: 0\n"
        "🔄 Dublikatlar: 0\n"
        "📊 Daily Digests: 0\n"
        "🤖 AI So'rovlar: 0\n"
        "❌ Xatolar: 0"
    )
    await callback.message.edit_text(stats_text, parse_mode="Markdown")
    await callback.answer()


@admin_router.callback_query(F.data == "admin_ai")
async def admin_ai(callback: types.CallbackQuery):
    """Show AI settings."""
    keyboard = get_ai_settings_keyboard(
        current_provider=settings.AI_PROVIDER,
        current_model=settings.AI_MODEL
    )
    await callback.message.edit_text(
        "🤖 **AI Sozlamalari**\n\n"
        f"📡 Joriy Provider: `{settings.AI_PROVIDER}`\n"
        f"🧠 Joriy Model: `{settings.AI_MODEL}`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_prompts")
async def admin_prompts(callback: types.CallbackQuery):
    """Show prompt management."""
    await callback.message.edit_text(
        "📝 **Prompt Sozlamalari**\n\n"
        "O'zgartirish uchun promptni tanlang:",
        parse_mode="Markdown",
        reply_markup=get_prompt_management_keyboard()
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_sources")
async def admin_sources(callback: types.CallbackQuery):
    """Show source management."""
    await callback.message.edit_text(
        "📰 **Yangiliklar Manbalari**\n\n"
        "RSS manbalarini boshqarish:",
        parse_mode="Markdown",
        reply_markup=get_source_management_keyboard()
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_digest")
async def admin_digest(callback: types.CallbackQuery):
    """Show digest settings."""
    await callback.message.edit_text(
        "📅 **Daily Digest Sozlamalari**\n\n"
        f"⏰ Joriy vaqt: {settings.DIGEST_TIME}\n"
        f"🌍 Vaqt zonasi: {settings.DIGEST_TIMEZONE}",
        parse_mode="Markdown",
        reply_markup=get_digest_settings_keyboard()
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_system")
async def admin_system(callback: types.CallbackQuery):
    """Show system settings."""
    await callback.message.edit_text(
        "⚙️ **Tizim Sozlamalari**\n\n"
        "Tizim holatini tekshirish:",
        parse_mode="Markdown",
        reply_markup=get_system_settings_keyboard()
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("cancel_action"))
async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
    """Cancel current action."""
    await state.clear()
    await callback.message.edit_text(
        "❌ Amal bekor qilindi.",
        reply_markup=get_main_admin_keyboard()
    )
    await callback.answer()
