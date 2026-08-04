"""Daily digest model — summary of news for a given day."""

from datetime import date

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class DailyDigest(Base, TimestampMixin):
    """A daily digest — AI-generated summary of all news for a specific date."""

    __tablename__ = "daily_digests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    digest_date: Mapped[date] = mapped_column(DateTime, unique=True, nullable=False)
    news_count: Mapped[int] = mapped_column(nullable=False, default=0)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    most_bullish: Mapped[str | None] = mapped_column(Text, nullable=True)
    most_bearish: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(default=False, nullable=False)
    channel_message_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    telegraph_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<DailyDigest date={self.digest_date} count={self.news_count}>"
