"""Scheduler setup — APScheduler with news collection, live prices, and digest jobs."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.core.config import settings
from src.scheduler.jobs import (
    collect_and_publish_news,
    collect_news,
    generate_telegraph_digest,
    send_economic_calendar,
    send_token_unlocks,
    update_live_prices,
)
from src.telegram_bot.publisher import Publisher

logger = logging.getLogger(__name__)

# Module-level reference so admin panel changes can reschedule the digest job.
_scheduler: AsyncIOScheduler | None = None

DIGEST_JOB_ID = "telegraph_digest"
_DEFAULT_TIMES = ["08:00", "12:00", "18:00", "22:00"]

# Full/short weekday names → APScheduler day_of_week index (sun=0 ... sat=6)
_WEEKDAY_MAP = {
    "sunday": "sun", "monday": "mon", "tuesday": "tue", "wednesday": "wed",
    "thursday": "thu", "friday": "fri", "saturday": "sat",
    "yakshanba": "sun", "dushanba": "mon", "seshanba": "tue",
    "chorshanba": "wed", "payshanba": "thu", "juma": "fri", "shanba": "sat",
}


def _normalize_weekday(name: str) -> str:
    """Normalize a weekday name to a 3-letter APScheduler abbreviation or 0-6 index."""
    key = (name or "").strip().lower()
    if not key:
        return "sun"
    if key in _WEEKDAY_MAP:
        return _WEEKDAY_MAP[key]
    if key.isdigit():
        idx = int(key)
        if 0 <= idx <= 6:
            return key
    elif len(key) >= 3:
        short = key[:3]
        if short in ("sun", "mon", "tue", "wed", "thu", "fri", "sat"):
            return short
    logger.warning("Unknown weekday name %r — falling back to 'sun'", name)
    return "sun"


def _parse_times(schedule_times: list[str]) -> set[tuple[int, int]]:
    """Parse schedule times into a set of (hour, minute) pairs."""
    pairs: set[tuple[int, int]] = set()
    for t in schedule_times:
        parts = t.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                pairs.add((h, m))
    return pairs


def _build_digest_trigger(hour: int, minute: int) -> CronTrigger:
    """Build a CronTrigger for one exact digest time."""
    return CronTrigger(
        hour=str(hour),
        minute=str(minute),
        timezone=settings.digest_timezone,
    )


def _configure_digest_jobs(scheduler: AsyncIOScheduler, publisher: Publisher, schedule_times: list[str]) -> None:
    """Remove any existing digest jobs and add one cron job per exact time.

    One job per HH:MM avoids the cartesian-product bug that a single cron
    trigger with multiple hours/minutes would introduce for mixed times.
    """
    for job in scheduler.get_jobs():
        if job.id.startswith(f"{DIGEST_JOB_ID}_"):
            scheduler.remove_job(job.id)

    pairs = sorted(_parse_times(schedule_times))
    if not pairs:
        pairs = sorted(_parse_times(_DEFAULT_TIMES))

    for hour, minute in pairs:
        job_id = f"{DIGEST_JOB_ID}_{hour:02d}:{minute:02d}"
        scheduler.add_job(
            generate_telegraph_digest,
            trigger=_build_digest_trigger(hour, minute),
            args=[publisher],
            id=job_id,
            name=f"Generate Telegraph digest {hour:02d}:{minute:02d}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )


def create_scheduler(publisher: Publisher) -> AsyncIOScheduler:
    """Create and configure the APScheduler instance.

    Publishing mode is controlled by PUBLISH_MODE:

    - ``instant`` (default): collect_and_publish_news — every news item is
      analyzed and sent to the channel as soon as it is collected. No digests.
    - ``digest``: collect_news 24/7 (saved to DB, no publishing) + a
      generate_telegraph_digest cron job per scheduled time (default
      08:00, 12:00, 18:00, 22:00).

    Live prices job runs in both modes.
    """
    global _scheduler

    scheduler = AsyncIOScheduler(timezone=settings.digest_timezone)
    mode = (settings.publish_mode or "instant").strip().lower()
    if mode not in ("instant", "digest"):
        logger.warning("Unknown PUBLISH_MODE %r — falling back to 'instant'", settings.publish_mode)
        mode = "instant"

    if mode == "digest":
        # Job 1: Collect news periodically (saved to DB, picked up by digests)
        scheduler.add_job(
            collect_news,
            trigger=IntervalTrigger(seconds=settings.news_check_interval),
            id="collect_news",
            name="Collect news (24/7)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(),
        )
    else:
        # Job 1: Collect + publish each item immediately to the channel
        scheduler.add_job(
            collect_and_publish_news,
            trigger=IntervalTrigger(seconds=settings.news_check_interval),
            args=[publisher],
            id="collect_and_publish",
            name="Collect and publish news",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(),
        )

    # Job 2: Update live prices (pinned message)
    live_price_interval = getattr(settings, 'live_price_interval', 60)
    scheduler.add_job(
        update_live_prices,
        trigger=IntervalTrigger(seconds=live_price_interval),
        id="live_prices",
        name="Update live crypto prices",
        replace_existing=True,
        max_instances=1,
    )

    # Job 3: Generate Telegraph digest at each scheduled time (digest mode only)
    if mode == "digest":
        try:
            schedule_times = list(getattr(settings, "digest_schedule_list", _DEFAULT_TIMES))
        except Exception:
            schedule_times = list(_DEFAULT_TIMES)
        _configure_digest_jobs(scheduler, publisher, schedule_times)

    # Job 4: Weekly economic calendar post
    if settings.economic_calendar_enabled:
        try:
            day = _normalize_weekday(settings.calendar_post_day or "sunday")
            time_parts = (settings.calendar_post_time or "20:00").split(":")
            cal_hour, cal_minute = int(time_parts[0]), int(time_parts[1])
            scheduler.add_job(
                send_economic_calendar,
                trigger=CronTrigger(day_of_week=day, hour=str(cal_hour), minute=str(cal_minute),
                                    timezone=settings.digest_timezone),
                args=[publisher],
                id="economic_calendar",
                name="Weekly economic calendar",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        except Exception as e:
            logger.error("Failed to schedule economic calendar: %s", e)

    # Job 5: Weekly top token unlocks post
    if getattr(settings, "token_unlocks_enabled", True):
        try:
            u_day = _normalize_weekday(settings.unlocks_post_day or "sunday")
            u_parts = (settings.unlocks_post_time or "20:15").split(":")
            scheduler.add_job(
                send_token_unlocks,
                trigger=CronTrigger(day_of_week=u_day, hour=str(int(u_parts[0])),
                                    minute=str(int(u_parts[1])), timezone=settings.digest_timezone),
                args=[publisher],
                id="token_unlocks",
                name="Weekly top token unlocks",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        except Exception as e:
            logger.error("Failed to schedule token unlocks: %s", e)

    _scheduler = scheduler

    if mode == "digest":
        logger.info(
            "Scheduler configured (digest): news every %ds, live prices every %ds, digest at %s (%s)",
            settings.news_check_interval,
            live_price_interval,
            ", ".join(schedule_times),
            settings.digest_timezone,
        )
    else:
        logger.info(
            "Scheduler configured (instant): news every %ds, live prices every %ds — publishing immediately, no digests",
            settings.news_check_interval,
            live_price_interval,
        )

    return scheduler


async def reschedule_digest_jobs() -> list[str] | None:
    """Re-read digest schedule times from DB and reschedule the digest jobs.

    Called from the admin panel after the schedule is changed, so changes take
    effect immediately without a bot restart. Returns the new schedule list,
    or None if there is no running scheduler / no stored schedule.
    """
    global _scheduler
    try:
        from src.digest.schedule import get_schedule_times
        times = await get_schedule_times()
    except Exception as e:
        logger.error("Failed to load schedule for rescheduling: %s", e)
        return None

    if _scheduler is None:
        logger.warning("Scheduler not running — schedule saved, applied on next start")
        return times

    try:
        # Reuse the publisher bound to an existing digest job
        publisher = None
        for job in _scheduler.get_jobs():
            if job.id.startswith(f"{DIGEST_JOB_ID}_") and job.args:
                publisher = job.args[0]
                break
        _configure_digest_jobs(_scheduler, publisher, times)
        logger.info("Digest jobs rescheduled to: %s", ", ".join(times))
        return times
    except Exception as e:
        logger.error("Failed to reschedule digest jobs: %s", e)
        return times
