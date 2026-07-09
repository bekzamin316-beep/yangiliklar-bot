"""News and source models — core business entities."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class News(Base, TimestampMixin):
    """A single news item — collected, analyzed, and published."""

    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI-generated metadata
    importance_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Publication status
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    channel_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<News id={self.id} title={self.title[:40]} importance={self.importance_score}>"


class RSSSource(Base, TimestampMixin):
    """An RSS feed source configured for news collection."""

    __tablename__ = "rss_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_fetched_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<RSSSource name={self.name} active={self.is_active}>"


class NewsSource(Base, TimestampMixin):
    """A general news source (API, RSS, scraper)."""

    __tablename__ = "news_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # rss, api, scraper
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<NewsSource name={self.name} type={self.source_type}>"
