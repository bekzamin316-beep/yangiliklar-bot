"""Digest schedule helpers.

Times are stored in the DB ``settings`` table (key ``digest_schedule_times``)
so admins can change them at runtime without editing .env or restarting.
The .env ``DIGEST_SCHEDULE_TIMES`` value is used as the default on first run.
"""

import logging
from datetime import datetime, timedelta, timezone

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import SettingsRepository

logger = logging.getLogger(__name__)

# Settings DB keys
KEY_SCHEDULE_TIMES = "digest_schedule_times"
KEY_LAST_DIGEST_AT = "last_digest_sent_at"
KEY_TELEGRAPH_TOKEN = "telegraph_access_token"


def _parse_times(value: str | None) -> list[str]:
    """Parse a comma-separated 'HH:MM,HH:MM' string into a validated sorted list."""
    if not value:
        return []
    times = [t.strip() for t in value.split(",") if t.strip()]
    valid: list[str] = []
    for t in times:
        parts = t.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                valid.append(f"{h:02d}:{m:02d}")
    return sorted(set(valid))


async def get_schedule_times() -> list[str]:
    """Return the active digest schedule times (sorted 'HH:MM' list).

    Falls back to env default ``DIGEST_SCHEDULE_TIMES``, then to the legacy
    ``DIGEST_HOUR:DIGEST_MINUTE`` pair, then to 08:00,12:00,18:00,22:00.
    """
    try:
        async with get_session() as session:
            repo = SettingsRepository(session)
            stored = await repo.get_value(KEY_SCHEDULE_TIMES)
        if stored:
            times = _parse_times(stored)
            if times:
                return times
    except Exception as e:
        logger.warning("Could not read digest schedule from DB: %s", e)

    env_times = _parse_times(settings.digest_schedule_times)
    if env_times:
        return env_times

    legacy = f"{settings.digest_hour:02d}:{settings.digest_minute:02d}"
    if settings.digest_hour or settings.digest_minute:
        return [legacy]

    return ["08:00", "12:00", "18:00", "22:00"]


async def set_schedule_times(value: str) -> list[str]:
    """Validate and persist a new schedule (e.g. '08:00,12:00,18:00,22:00')."""
    times = _parse_times(value)
    if not times:
        raise ValueError("Hech bo'lmaganda bitta to'g'ri vaqt kiriting (HH:MM, vergul bilan)")
    normalized = ",".join(times)
    async with get_session() as session:
        repo = SettingsRepository(session)
        await repo.set_value(
            KEY_SCHEDULE_TIMES,
            normalized,
            value_type="string",
            description="Digest yuborish vaqtlari (HH:MM, vergul bilan ajratilgan)",
        )
    logger.info("Digest schedule updated: %s", normalized)
    return times


async def get_last_digest_time() -> datetime | None:
    """Return the UTC datetime of the last successfully sent digest (or None)."""
    try:
        async with get_session() as session:
            repo = SettingsRepository(session)
            stored = await repo.get_value(KEY_LAST_DIGEST_AT)
        if not stored:
            return None
        return datetime.fromisoformat(stored)
    except Exception as e:
        logger.warning("Could not read last digest time: %s", e)
        return None


async def set_last_digest_time(dt: datetime | None = None) -> None:
    """Persist the time of the last sent digest (UTC).

    Pass None to clear the timestamp (used when resetting the window).
    """
    value = dt.isoformat() if dt else ""
    async with get_session() as session:
        repo = SettingsRepository(session)
        await repo.set_value(
            KEY_LAST_DIGEST_AT,
            value,
            value_type="string",
            description="Oxirgi muvaffaqiyatli digest yuborilgan vaqt (UTC ISO)",
        )


async def get_news_since_window() -> tuple[datetime, datetime]:
    """Return the (since, now) UTC window for the next digest.

    ``since`` is the last digest time if available, otherwise 24 hours back —
    so on the very first run nothing is missed.
    """
    last = await get_last_digest_time()
    now = datetime.now(timezone.utc)
    since = last if last is not None else now - timedelta(hours=24)
    # Guard against pathological values
    if since > now:
        since = now - timedelta(hours=24)
    return since, now
