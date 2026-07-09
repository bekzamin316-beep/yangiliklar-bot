"""Raw news item — collected from any source before DB processing."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime


def _normalize(text: str) -> str:
    """Normalize text for dedup: lowercase, strip HTML, collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", text)  # strip HTML tags
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)  # collapse whitespace
    return text


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
        """Generate a SHA-256 hash of normalized title + content for deduplication."""
        norm_title = _normalize(self.title)
        norm_content = _normalize(self.content[:500])
        raw = f"{norm_title}:{norm_content}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def url_hash(self) -> str:
        """Generate a hash of the URL for deduplication by source URL."""
        norm_url = self.url.strip().lower()
        norm_url = re.sub(r"https?://(www\.)?", "", norm_url)
        norm_url = norm_url.rstrip("/")
        return hashlib.sha256(norm_url.encode("utf-8")).hexdigest()
