"""Telegram keyboards for admin panel."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_admin_keyboard() -> InlineKeyboardMarkup:
    """Main admin panel keyboard."""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📊 Statistika", callback_data="admin_stats")
    builder.button(text="📰 Yangiliklar Manbalari", callback_data="admin_sources")
    builder.button(text="🤖 AI Sozlamalari", callback_data="admin_ai")
    builder.button(text="📝 Prompt Sozlamalari", callback_data="admin_prompts")
    builder.button(text="📅 Daily Digest", callback_data="admin_digest")
    builder.button(text="⚙ Tizim Sozlamalari", callback_data="admin_system")
    
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def get_ai_settings_keyboard(current_provider: str, current_model: str) -> InlineKeyboardMarkup:
    """AI settings keyboard."""
    builder = InlineKeyboardBuilder()
    
    builder.button(text=f"📡 Provider: {current_provider}", callback_data="ai_change_provider")
    builder.button(text=f"🧠 Model: {current_model}", callback_data="ai_change_model")
    builder.button(text="🔄 Fallback Tartibi", callback_data="ai_fallback_order")
    builder.button(text="🧪 AI Test", callback_data="ai_test")
    builder.button(text="➕ Model Qo'shish", callback_data="ai_add_model")
    builder.button(text="➖ Model O'chirish", callback_data="ai_delete_model")
    builder.button(text="🔙 Orqaga", callback_data="admin_main")
    
    builder.adjust(1, 1, 1, 1, 2)
    return builder.as_markup()


def get_provider_selection_keyboard(providers: list) -> InlineKeyboardMarkup:
    """Provider selection keyboard."""
    builder = InlineKeyboardBuilder()
    
    for provider in providers:
        builder.button(text=f"{provider}", callback_data=f"ai_set_provider_{provider}")
    
    builder.button(text="🔙 Orqaga", callback_data="admin_ai")
    builder.adjust(2)
    return builder.as_markup()


def get_model_management_keyboard(models: list) -> InlineKeyboardMarkup:
    """Model management keyboard."""
    builder = InlineKeyboardBuilder()
    
    for model in models[:10]:  # Show first 10 models
        builder.button(text=f"🧠 {model}", callback_data=f"ai_set_model_{model}")
    
    builder.button(text="🔙 Orqaga", callback_data="admin_ai")
    builder.adjust(2)
    return builder.as_markup()


def get_prompt_management_keyboard() -> InlineKeyboardMarkup:
    """Prompt management keyboard."""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📰 News Prompt", callback_data="prompt_edit_news")
    builder.button(text="📊 Digest Prompt", callback_data="prompt_edit_digest")
    builder.button(text="⚠️ Alert Prompt", callback_data="prompt_edit_alert")
    builder.button(text="🌐 Translation Prompt", callback_data="prompt_edit_translation")
    builder.button(text="📝 Summary Prompt", callback_data="prompt_edit_summary")
    builder.button(text="🔙 Orqaga", callback_data="admin_main")
    
    builder.adjust(1, 1, 1, 1, 2)
    return builder.as_markup()


def get_source_management_keyboard() -> InlineKeyboardMarkup:
    """RSS source management keyboard."""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="➕ RSS Qo'shish", callback_data="rss_add")
    builder.button(text="🗑️ RSS O'chirish", callback_data="rss_delete")
    builder.button(text="✅ RSS Enable", callback_data="rss_enable")
    builder.button(text="❌ RSS Disable", callback_data="rss_disable")
    builder.button(text="📋 RSS Ro'yxati", callback_data="rss_list")
    builder.button(text="🧪 RSS Test", callback_data="rss_test")
    builder.button(text="🔙 Orqaga", callback_data="admin_main")
    
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def get_digest_settings_keyboard() -> InlineKeyboardMarkup:
    """Digest settings keyboard."""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="⏰ Vaqtni O'zgartirish", callback_data="digest_change_time")
    builder.button(text="📊 Bugungi Digest", callback_data="digest_view_today")
    builder.button(text="📜 Tarixni Ko'rish", callback_data="digest_history")
    builder.button(text="🔙 Orqaga", callback_data="admin_main")
    
    builder.adjust(1, 1, 2)
    return builder.as_markup()


def get_system_settings_keyboard() -> InlineKeyboardMarkup:
    """System settings keyboard."""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="💾 Database Status", callback_data="system_db_status")
    builder.button(text="🔴 Redis Status", callback_data="system_redis_status")
    builder.button(text="📡 RSS Status", callback_data="system_rss_status")
    builder.button(text="🤖 AI Status", callback_data="system_ai_status")
    builder.button(text="📊 Metrics", callback_data="system_metrics")
    builder.button(text="📋 Loglar", callback_data="system_logs")
    builder.button(text="🔙 Orqaga", callback_data="admin_main")
    
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Cancel action keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Bekor qilish", callback_data="cancel_action")
    return builder.as_markup()


def get_confirm_keyboard(confirm_callback: str, cancel_callback: str = "cancel_action") -> InlineKeyboardMarkup:
    """Confirmation keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data=confirm_callback)
    builder.button(text="❌ Bekor qilish", callback_data=cancel_callback)
    builder.adjust(2)
    return builder.as_markup()


def get_back_keyboard(back_callback: str = "admin_main") -> InlineKeyboardMarkup:
    """Back button keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Orqaga", callback_data=back_callback)
    return builder.as_markup()
