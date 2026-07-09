"""FSM states for admin panel flows."""

from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """Admin panel FSM states."""

    waiting_for_admin_password = State()
    waiting_for_rss_url = State()
    waiting_for_rss_name = State()
    waiting_for_digest_time = State()
    waiting_for_prompt_edit = State()
    waiting_for_ai_model = State()
    waiting_for_channel_post = State()


class LivePriceStates(StatesGroup):
    """Live prices admin FSM states."""

    editing_coins = State()
    editing_interval = State()


class UserStates(StatesGroup):
    """User-facing FSM states (if needed in future)."""

    pass
