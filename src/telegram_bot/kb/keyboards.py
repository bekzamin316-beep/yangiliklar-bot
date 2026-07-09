"""Inline keyboards for admin panel and user bot."""

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ─── User keyboards ────────────────────────────────────────────

def get_user_start_keyboard() -> InlineKeyboardBuilder:
    """Keyboard shown after /start for regular users."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📰 Yangiliklar", callback_data="user_news")
    kb.button(text="📊 Statistika", callback_data="user_stats")
    kb.button(text="ℹ️ Yordam", callback_data="user_help")
    kb.adjust(2, 1)
    return kb


# ─── Admin keyboards ───────────────────────────────────────────

def get_admin_main_keyboard() -> InlineKeyboardBuilder:
    """Main admin panel menu."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Kanalga xabar", callback_data="admin_channel_post")
    kb.button(text="📊 Statistika", callback_data="admin_stats")
    kb.button(text="📰 Yangiliklar", callback_data="admin_news")
    kb.button(text="🔗 RSS Manbalar", callback_data="admin_sources")
    kb.button(text="🤖 AI Sozlamalar", callback_data="admin_ai")
    kb.button(text="📅 Digest", callback_data="admin_digest")
    kb.button(text="💰 Live Narxlar", callback_data="admin_live_prices")
    kb.button(text="📋 Loglar", callback_data="admin_logs")
    kb.button(text="⚙️ Tizim", callback_data="admin_system")
    kb.adjust(2, 2, 2, 2, 1)
    return kb


def get_admin_news_keyboard() -> InlineKeyboardBuilder:
    """Admin news management submenu."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Yangiliklarni yuborish", callback_data="admin_publish_now")
    kb.button(text="📋 Kutilayotgan yangiliklar", callback_data="admin_pending_news")
    kb.button(text="🗑 O'chirish", callback_data="admin_delete_news")
    kb.button(text="🔙 Orqaga", callback_data="admin_main")
    kb.adjust(1, 1, 1)
    return kb


def get_admin_sources_keyboard(sources: list) -> InlineKeyboardBuilder:
    """Dynamic keyboard listing RSS sources."""
    kb = InlineKeyboardBuilder()
    for i, src in enumerate(sources):
        status = "✅" if src.is_active else "❌"
        kb.button(text=f"{status} {src.name}", callback_data=f"source_{src.id}")
    kb.button(text="➕ Yangi manba qo'shish", callback_data="rss_add")
    kb.button(text="🔄 Yangilash", callback_data="rss_refresh")
    kb.button(text="🔙 Orqaga", callback_data="admin_main")
    kb.adjust(1)
    return kb


def get_source_detail_keyboard(source_id: int, is_active: bool) -> InlineKeyboardBuilder:
    """Keyboard for a single RSS source detail view."""
    kb = InlineKeyboardBuilder()
    toggle_text = "❌ O'chirish" if is_active else "✅ Yoqish"
    kb.button(text=toggle_text, callback_data=f"toggle_source_{source_id}")
    kb.button(text="🗑 O'chirish", callback_data=f"delete_source_{source_id}")
    kb.button(text="🔙 Orqaga", callback_data="admin_sources")
    kb.adjust(2, 1)
    return kb


def get_admin_ai_keyboard() -> InlineKeyboardBuilder:
    """Admin AI settings submenu."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔧 Provayder", callback_data="admin_ai_provider")
    kb.button(text="🧠 Model", callback_data="admin_ai_model")
    kb.button(text="📝 Promptlar", callback_data="admin_ai_prompts")
    kb.button(text="✏️ Prompt o'zgartirish", callback_data="admin_ai_prompt_edit")
    kb.button(text="🧪 Test", callback_data="admin_ai_test")
    kb.button(text="🔙 Orqaga", callback_data="admin_main")
    kb.adjust(2, 2, 2)
    return kb


def get_admin_digest_keyboard() -> InlineKeyboardBuilder:
    """Admin digest settings submenu."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🕐 Vaqtni o'zgartirish", callback_data="digest_change_time")
    kb.button(text="📤 Hozir yuborish", callback_data="digest_send_now")
    kb.button(text="📋 Oxirgi digestlar", callback_data="digest_history")
    kb.button(text="🔙 Orqaga", callback_data="admin_main")
    kb.adjust(1, 1, 1)
    return kb


def get_admin_live_prices_keyboard() -> InlineKeyboardBuilder:
    """Admin live prices settings submenu."""
    kb = InlineKeyboardBuilder()
    kb.button(text="💊 Tangalarni o'zgartirish", callback_data="live_coins_edit")
    kb.button(text="⏱ Intervalni o'zgartirish", callback_data="live_interval_edit")
    kb.button(text="🔄 Hozir yangilash", callback_data="live_refresh_now")
    kb.button(text="📊 Joriy holat", callback_data="live_status")
    kb.button(text="🔙 Orqaga", callback_data="admin_main")
    kb.adjust(1, 1, 1, 1)
    return kb


def get_admin_system_keyboard() -> InlineKeyboardBuilder:
    """Admin system monitoring submenu."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🗄 Database", callback_data="sys_db")
    kb.button(text="📡 Redis", callback_data="sys_redis")
    kb.button(text="📰 RSS", callback_data="sys_rss")
    kb.button(text="🤖 AI", callback_data="sys_ai")
    kb.button(text="📊 Metrikalar", callback_data="sys_metrics")
    kb.button(text="🔙 Orqaga", callback_data="admin_main")
    kb.adjust(2, 2, 1)
    return kb


def get_back_keyboard(callback_data: str = "admin_main") -> InlineKeyboardBuilder:
    """Simple back button."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Orqaga", callback_data=callback_data)
    return kb


def get_cancel_keyboard() -> InlineKeyboardBuilder:
    """Cancel button for FSM flows."""
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Bekor qilish", callback_data="cancel_action")
    return kb


def get_pin_keyboard(entered: str = "") -> InlineKeyboardBuilder:
    """PIN pad keyboard for 5-digit password entry.

    Shows digits 0-9 in a phone-layout grid, plus confirm and clear buttons.
    `entered` tracks how many digits have been input (shown as ● dots).
    """
    kb = InlineKeyboardBuilder()
    # Phone-style layout: 1-9 in 3x3 grid, then 0 on center bottom
    for digit in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        kb.button(text=str(digit), callback_data=f"digit_{digit}")
    kb.button(text="🗑 Tozalash", callback_data="pin_clear")
    kb.button(text="0", callback_data="digit_0")
    kb.button(text="✅ Tasdiqlash", callback_data="pin_confirm")
    kb.adjust(3, 3, 3, 3)  # rows: [1,2,3] [4,5,6] [7,8,9] [clear,0,confirm]
    return kb
