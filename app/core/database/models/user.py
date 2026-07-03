"""User and Admin models."""

from sqlalchemy import Column, Integer, String, Boolean, BigInteger
from app.core.database.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User model for bot users."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    def __repr__(self):
        return f"<User {self.telegram_id} - {self.username}>"


class Admin(Base, TimestampMixin):
    """Admin model for bot administrators."""

    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    permissions = Column(String(1000), default="all")  # JSON string of permissions
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Admin {self.telegram_id} - {self.username}>"
