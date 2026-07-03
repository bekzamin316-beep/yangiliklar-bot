"""AI Provider, Model, and Prompt models."""

from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database.models.base import Base, TimestampMixin


class AIProvider(Base, TimestampMixin):
    """AI Provider configuration model."""

    __tablename__ = "ai_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)  # openrouter, groq, gemini, etc.
    api_key_env = Column(String(100), nullable=False)  # Environment variable name for API key
    base_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    is_primary = Column(Boolean, default=False)
    priority = Column(Integer, default=99)  # Lower number = higher priority
    request_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    last_used = Column(DateTime, nullable=True)
    config = Column(JSONB, default=dict)  # Additional provider-specific config

    def __repr__(self):
        return f"<AIProvider {self.name}>"


class AIModel(Base, TimestampMixin):
    """AI Model configuration model."""

    __tablename__ = "ai_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(Integer, nullable=False)  # References ai_providers.id
    model_name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    max_tokens = Column(Integer, default=4096)
    temperature = Column(Float, default=0.7)
    usage_count = Column(Integer, default=0)
    config = Column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="unique_provider_model"),
    )

    def __repr__(self):
        return f"<AIModel {self.model_name}>"


class AIPrompt(Base, TimestampMixin):
    """AI Prompt templates stored in database."""

    __tablename__ = "ai_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)  # news_prompt, digest_prompt, etc.
    template = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    variables = Column(JSONB, default=list)  # List of expected variables

    def __repr__(self):
        return f"<AIPrompt {self.name} v{self.version}>"
