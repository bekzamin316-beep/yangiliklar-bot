"""Telegram bot states for conversation handling."""

from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """Admin panel conversation states."""
    waiting_for_rss_url = State()
    waiting_for_rss_name = State()
    waiting_for_model_name = State()
    waiting_for_prompt_edit = State()
    waiting_for_digest_time = State()
    waiting_for_api_key = State()


class PromptEditStates(StatesGroup):
    """Prompt editing states."""
    editing_news_prompt = State()
    editing_digest_prompt = State()
    editing_alert_prompt = State()
    editing_translation_prompt = State()
    editing_summary_prompt = State()
