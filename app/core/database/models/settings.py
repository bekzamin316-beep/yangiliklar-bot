"""Settings model for bot configuration."""

from sqlalchemy import Column, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database.models.base import Base, TimestampMixin


class Settings(Base, TimestampMixin):
    """Bot settings stored in database."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    value_type = Column(String(50), default="string")  # string, int, float, bool, json
    description = Column(Text, nullable=True)
    is_editable = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Settings {self.key}>"
