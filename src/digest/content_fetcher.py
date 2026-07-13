"""Fetch original content from news sources for digest generation.

- Telegram channels: uses Telethon to read original posts
- Websites: uses httpx + BeautifulSoup to extract article text
"""

import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from telethon import TelegramClient
from telethon.sessions import StringSession

from src.core.config import settings

logger = logging.getLogger(__name__)

# Regex to detect Telegram links in source_url
_TELEGRAM_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,})/(\d+)",
)


class ContentFetcher:
    """Fetches original article/post text from news source URLs."""

    def __init__(self):
        self._tl_client: TelegramClient | None = None
        self._tl_connected = False

    async def _get_telethon_client(self) -> TelegramClient | None:
        """Lazily create and connect a Telethon client using StringSession."""
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            logger.debug("Telethon not configured (no api_id/api_hash), skipping Telegram fetches")
            return None

        if self._tl_client and self._tl_connected:
            return self._tl_client

        try:
            # Use StringSession (stored in env var) instead of file-based session
            session_str = getattr(settings, 'telegram_session_string', '') or ''
            session = StringSession(session_str) if session_str else settings.telegram_session_name

            client = TelegramClient(
                session,
                settings.telegram_api_id,
                settings.telegram_api_hash,
            )
            await client.connect()

            if not await client.is_user_authorized():
                logger.warning("Telethon session not authorized — digest cannot read Telegram channel posts. "
                               "Set TELEGRAM_SESSION_STRING env var with a valid StringSession.")
                await client.disconnect()
                return None

            self._tl_client = client
            self._tl_connected = True
            logger.info("Telethon client connected and authorized")
            return client

        except Exception as e:
            logger.error("Failed to connect Telethon client: %s", e)
            return None

    async def close(self) -> None:
        """Disconnect the Telethon client."""
        if self._tl_client and self._tl_connected:
            await self._tl_client.disconnect()
            self._tl_connected = False

    # ── Telegram channel posts ─────────────────────────────

    def _parse_telegram_link(self, url: str) -> tuple[str, int] | None:
        """Extract (channel_username, message_id) from a t.me link."""
        m = _TELEGRAM_LINK_RE.search(url)
        if m:
            return m.group(1), int(m.group(2))
        return None

    async def fetch_telegram_post(self, url: str) -> str:
        """Read the full text of a Telegram channel post via Telethon."""
        client = await self._get_telethon_client()
        if not client:
            return ""

        parsed = self._parse_telegram_link(url)
        if not parsed:
            return ""

        channel, msg_id = parsed
        try:
            msg = await client.get_messages(channel, ids=msg_id)
            if msg and msg.text:
                return msg.text
            return ""
        except Exception as e:
            logger.warning("Telethon failed to read %s/%d: %s", channel, msg_id, e)
            return ""

    async def fetch_channel_posts_today(self, channel_username: str, hours: int = 24) -> list[dict]:
        """Read all posts from a Telegram channel from the last N hours.

        Returns a list of dicts: {text, date, msg_id, channel, link}
        """
        client = await self._get_telethon_client()
        if not client:
            return []

        try:
            from datetime import timedelta
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
            posts = []
            async for msg in client.iter_messages(channel_username, offset_date=since, reverse=True):
                if msg.text:
                    posts.append({
                        "text": msg.text,
                        "date": msg.date.isoformat() if msg.date else "",
                        "msg_id": msg.id,
                        "channel": channel_username,
                        "link": f"https://t.me/{channel_username}/{msg.id}",
                    })
            logger.info("Read %d posts from channel %s (last %dh)", len(posts), channel_username, hours)
            return posts
        except Exception as e:
            logger.warning("Telethon failed to read channel %s: %s", channel_username, e)
            return []

    # ── Web articles ────────────────────────────────────────

    async def fetch_web_article(self, url: str) -> str:
        """Fetch and extract main text from a web article URL."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text

            soup = BeautifulSoup(html, "html.parser")

            # Remove noise elements
            for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "form", "iframe"]):
                tag.decompose()

            # Try known article containers first
            for container in soup.find_all(["article", "[role='main']", "main", ".post-content", ".entry-content", ".article-body"]):
                text = container.get_text(separator="\n", strip=True)
                if len(text) > 200:
                    return text[:3000]

            # Fallback: largest text block
            best = ""
            for tag in soup.find_all(["div", "section", "p"]):
                text = tag.get_text(separator="\n", strip=True)
                if len(text) > len(best) and len(text) > 200:
                    best = text

            return best[:3000] if best else ""

        except Exception as e:
            logger.warning("Failed to fetch web article %s: %s", url, e)
            return ""

    # ── Unified fetch ───────────────────────────────────────

    async def fetch_source_content(self, url: str) -> str:
        """Fetch original content from a source URL (Telegram or web)."""
        if not url:
            return ""

        parsed = self._parse_telegram_link(url)
        if parsed:
            return await self.fetch_telegram_post(url)

        return await self.fetch_web_article(url)

    async def fetch_all_sources(self, news_items: list) -> dict[int, str]:
        """Fetch original content for all news items by their source_url.

        Returns dict: {news_id: original_content}
        """
        results: dict[int, str] = {}
        for item in news_items:
            source_url = getattr(item, "source_url", None)
            if source_url:
                content = await self.fetch_source_content(source_url)
                if content:
                    results[item.id] = content
        return results

    async def fetch_channel_sources(self, hours: int = 24) -> list[dict]:
        """Read posts from configured Telegram source channels.

        Returns raw post dicts for AI processing.
        """
        if not settings.digest_source_channels:
            return []

        channels = [c.strip().lstrip("@") for c in settings.digest_source_channels.split(",") if c.strip()]
        all_posts = []
        for ch in channels:
            posts = await self.fetch_channel_posts_today(ch, hours)
            all_posts.extend(posts)
        return all_posts
