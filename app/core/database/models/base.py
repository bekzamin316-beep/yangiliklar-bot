"""Base model for all database models."""

from datetime import datetime
from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class TimestampMixin:
    """Mixin for adding timestamp columns to models."""

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
