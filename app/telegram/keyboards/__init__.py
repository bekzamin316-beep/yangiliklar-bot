"""Telegram keyboards module initialization."""

from app.telegram.keyboards.admin_keyboard import (
    get_main_admin_keyboard,
    get_ai_settings_keyboard,
    get_provider_selection_keyboard,
    get_model_management_keyboard,
    get_prompt_management_keyboard,
    get_source_management_keyboard,
    get_digest_settings_keyboard,
    get_system_settings_keyboard,
    get_cancel_keyboard,
    get_confirm_keyboard,
    get_back_keyboard,
)

__all__ = [
    "get_main_admin_keyboard",
    "get_ai_settings_keyboard",
    "get_provider_selection_keyboard",
    "get_model_management_keyboard",
    "get_prompt_management_keyboard",
    "get_source_management_keyboard",
    "get_digest_settings_keyboard",
    "get_system_settings_keyboard",
    "get_cancel_keyboard",
    "get_confirm_keyboard",
    "get_back_keyboard",
]
