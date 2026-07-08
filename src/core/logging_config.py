"""Centralized logging with structlog."""

import logging
import sys
from pathlib import Path

import structlog

from src.core.config import settings


def setup_logging() -> None:
    """Configure structlog + stdlib logging."""

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Ensure log file exists (append mode)
    log_path = Path("/tmp/cnbot.log")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    # Configure stdlib logging to file + stdout
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=level,
        handlers=[
            logging.FileHandler(log_path, mode="a", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )