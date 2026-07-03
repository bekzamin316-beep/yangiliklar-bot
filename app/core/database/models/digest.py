"""Daily Digest model."""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database.models.base import Base, TimestampMixin


class DailyDigest(Base, TimestampMixin):
    """Daily digest model."""

    __tablename__ = "daily_digests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    digest_date = Column(DateTime, nullable=False, index=True)
    telegram_message_id = Column(BigInteger, nullable=True)
    telegram_post_url = Column(String(500), nullable=True)
    news_count = Column(Integer, default=0)
    news_items = Column(JSONB, default=list)  # List of news IDs included
    ai_summary = Column(Text, nullable=True)
    most_bullish = Column(Text, nullable=True)
    most_bearish = Column(Text, nullable=True)
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<DailyDigest {self.digest_date}>"
