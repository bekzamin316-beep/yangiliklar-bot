"""Scheduler setup — APScheduler with news collection and digest jobs."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.core.config import settings
from src.scheduler.jobs import collect_and_publish_news, generate_daily_digest
from src.telegram_bot.publisher import Publisher

logger = logging.getLogger(__name__)


def create_scheduler(publisher: Publisher) -> AsyncIOScheduler:
    """Create and configure the APScheduler instance.

    Jobs:
    1. collect_and_publish_news — every NEWS_CHECK_INTERVAL seconds
    2. generate_daily_digest — daily at DIGEST_HOUR:DIGEST_MINUTE
    """
    scheduler = AsyncIOScheduler(timezone=settings.digest_timezone)

    # Job 1: Collect and publish news periodically
    scheduler.add_job(
        collect_and_publish_news,
        trigger=IntervalTrigger(seconds=settings.news_check_interval),
        args=[publisher],
        id="collect_news",
        name="Collect and publish news",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(),
    )

    # Job 2: Generate daily digest
    scheduler.add_job(
        generate_daily_digest,
        trigger=CronTrigger(
            hour=settings.digest_hour,
            minute=settings.digest_minute,
        ),
        args=[publisher],
        id="daily_digest",
        name="Generate daily digest",
        replace_existing=True,
        max_instances=1,
    )

    logger.info(
        "Scheduler configured: news every %ds, digest at %02d:%02d %s",
        settings.news_check_interval,
        settings.digest_hour,
        settings.digest_minute,
        settings.digest_timezone,
    )

    return scheduler
