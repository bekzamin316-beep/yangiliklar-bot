"""Raw news item — collected from any source before DB processing."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawNewsItem:
    """A raw news item collected from RSS/API before processing."""

    title: str
    content: str
    url: str
    source_name: str
    published_at: datetime | None = None
    image_url: str | None = None
    author: str | None = None
    tags: list[str] = field(default_factory=list)

    def content_hash(self) -> str:
        """Generate a SHA-256 hash of title + content for deduplication."""
        import hashlib

        raw = f"{self.title}:{self.content[:500]}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
