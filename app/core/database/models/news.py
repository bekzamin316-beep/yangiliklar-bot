"""News and News Source models."""

from sqlalchemy import Column, Integer, String, Text, Float, Boolean, BigInteger, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database.models.base import Base, TimestampMixin


class News(Base, TimestampMixin):
    """News article model."""

    __tablename__ = "news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(1000), nullable=False)
    summary = Column(Text, nullable=False)
    analysis = Column(Text, nullable=True)
    source_name = Column(String(255), nullable=False)
    source_url = Column(String(1000), nullable=False)
    telegram_message_id = Column(BigInteger, nullable=True)
    telegram_post_url = Column(String(500), nullable=True)
    importance_score = Column(Float, default=0.0)
    sentiment = Column(String(50), default="neutral")  # bullish, bearish, neutral
    published_at = Column(DateTime, nullable=True)
    hash = Column(String(64), unique=True, nullable=False, index=True)
    digest_included = Column(Boolean, default=False)
    tags = Column(JSONB, default=list)
    raw_content = Column(Text, nullable=True)
    is_published = Column(Boolean, default=False)
    is_duplicate = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_news_importance", "importance_score"),
        Index("idx_news_sentiment", "sentiment"),
        Index("idx_news_published", "is_published"),
    )

    def __repr__(self):
        return f"<News {self.id} - {self.title[:50]}>"


class NewsSource(Base, TimestampMixin):
    """General news source model."""

    __tablename__ = "news_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    type = Column(String(50), nullable=False)  # rss, api
    url = Column(String(1000), nullable=False)
    is_active = Column(Boolean, default=True)
    last_checked = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<NewsSource {self.name}>"


class RSSSource(Base, TimestampMixin):
    """RSS feed source model."""

    __tablename__ = "rss_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(1000), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    last_fetched = Column(DateTime, nullable=True)
    fetch_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    def __repr__(self):
        return f"<RSSSource {self.name}>"
