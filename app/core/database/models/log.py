"""Log and SystemMetric models."""

from sqlalchemy import Column, Integer, String, Text, Float, DateTime, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database.models.base import Base, TimestampMixin


class Log(Base, TimestampMixin):
    """Application log entries."""

    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(50), nullable=False)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    module = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    details = Column(JSONB, default=dict)
    user_id = Column(BigInteger, nullable=True)

    def __repr__(self):
        return f"<Log {self.level} - {self.message[:50]}>"


class SystemMetric(Base, TimestampMixin):
    """System metrics for monitoring."""

    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    metric_type = Column(String(50), default="gauge")  # gauge, counter, histogram
    labels = Column(JSONB, default=dict)
    timestamp = Column(DateTime, nullable=False, index=True)

    def __repr__(self):
        return f"<SystemMetric {self.metric_name}={self.metric_value}>"
