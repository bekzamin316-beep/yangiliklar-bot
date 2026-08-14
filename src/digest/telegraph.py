"""Telegraph client — creates pages for digests using the Telegraph API.

An anonymous Telegraph account is created on first use (no user credentials
needed) and its access token is persisted in the DB ``settings`` table.

The Telegraph API requires page ``content`` to be a JSON array of Node
objects (or an HTML string). We build the page as HTML for readability and
convert it to a Node array with BeautifulSoup before sending — this matches
the subset of tags Telegraph supports.
"""

import html
import json
import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.core.config import settings
from src.core.database import get_session
from src.core.repositories import SettingsRepository
from src.digest.schedule import KEY_TELEGRAPH_TOKEN

logger = logging.getLogger(__name__)

# Telegraph content limit: 64KB of markup
_TELEGRAPH_CONTENT_LIMIT = 60 * 1024

# Tags Telegraph supports natively; anything else is unwrapped (children hoisted)
_TELEGRAPH_TAGS = {
    "h2", "h3", "h4", "p", "b", "i", "a", "ul", "ol", "li", "img", "code", "pre",
}


class TelegraphError(Exception):
    """Raised when the Telegraph API returns an error."""


class TelegraphClient:
    """Minimal async client for the Telegraph API (page creation only)."""

    def __init__(self) -> None:
        self._base = settings.telegraph_api_base.rstrip("/")
        self._token: str | None = None

    # ── Token management ──────────────────────────────────────

    async def _load_token(self) -> str:
        """Load the access token from DB, creating an account if needed."""
        if self._token:
            return self._token

        async with get_session() as session:
            repo = SettingsRepository(session)
            token = await repo.get_value(KEY_TELEGRAPH_TOKEN)

        if token:
            self._token = token
            return token

        token = await self._create_account()
        async with get_session() as session:
            repo = SettingsRepository(session)
            await repo.set_value(
                KEY_TELEGRAPH_TOKEN,
                token,
                value_type="string",
                description="Telegraph API access token (auto-created)",
            )
        self._token = token
        logger.info("Created new Telegraph account (token stored in DB)")
        return token

    async def _create_account(self) -> str:
        """Create an anonymous Telegraph account and return its access token."""
        params: dict[str, Any] = {
            "short_name": settings.telegraph_short_name,
            "author_name": settings.telegraph_author_name,
        }
        if settings.telegraph_author_url:
            params["author_url"] = settings.telegraph_author_url

        data = await self._api_call("createAccount", params=params)
        return data["access_token"]

    # ── Page creation ─────────────────────────────────────────

    async def create_page(self, title: str, content_html: str) -> str:
        """Create a page and return its public URL.

        Raises:
            TelegraphError: if the API rejects the request.
        """
        token = await self._load_token()

        if len(content_html.encode("utf-8")) > _TELEGRAPH_CONTENT_LIMIT:
            logger.warning(
                "Telegraph content is %.1fKB (limit %.0fKB) — truncating tail",
                len(content_html.encode("utf-8")) / 1024,
                _TELEGRAPH_CONTENT_LIMIT / 1024,
            )
            content_html = self._truncate_html(content_html, _TELEGRAPH_CONTENT_LIMIT)

        nodes = self._html_to_nodes(content_html)

        params = {
            "access_token": token,
            "title": title,
            "author_name": settings.telegraph_author_name,
            "content": json.dumps(nodes),
            "return_content": False,
        }
        data = await self._api_call("createPage", params=params)
        url = data.get("url", "")
        if not url:
            raise TelegraphError("Telegraph createPage returned no URL")
        logger.info("Telegraph page created: %s", url)
        return url

    async def upload_image(self, file_bytes: bytes) -> str | None:
        """Upload an image to Telegraph's CDN and return the ``src`` URL.

        The returned string is ready to embed as ``<img src="...">``.

        Returns ``None`` on failure so callers can gracefully skip the image.
        """
        # Detect image format from magic bytes
        if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            filename, content_type = "image.png", "image/png"
        elif file_bytes[:3] == b"\xff\xd8\xff":
            filename, content_type = "image.jpeg", "image/jpeg"
        elif file_bytes[:6] == b"GIF87a" or file_bytes[:6] == b"GIF89a":
            filename, content_type = "image.gif", "image/gif"
        else:
            filename, content_type = "image.png", "image/png"

        files = {"file": (filename, file_bytes, content_type)}
        upload_url = "https://telegra.ph/upload"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(upload_url, files=files)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            logger.error("Telegraph image upload failed: %s", e)
            return None
        except Exception as e:
            logger.error("Telegraph image upload unexpected error: %s", e)
            return None

        if not data.get("ok"):
            logger.error("Telegraph upload error: %s", data.get("error", "unknown"))
            return None

        results = data.get("result") or []
        if not results:
            logger.warning("Telegraph upload returned no result items")
            return None

        src = results[0].get("src", "")
        if not src:
            return None
        if not src.startswith("http"):
            src = "https:" + src
        logger.info("Telegraph image uploaded: %s", src)
        return src

    async def get_page(self, path: str) -> dict:
        """Fetch an existing page (title + source links) for inspection.

        Args:
            path: The page path from its URL (the part after telegra.ph/).

        Returns:
            A dict with keys ``title`` (str) and ``links`` (list of hrefs).
        """
        params = {"path": path, "return_content": True}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{self._base}/getPage", data=params)
                data = resp.json()
        except httpx.TimeoutException:
            logger.error("Telegraph getPage timed out")
            raise TelegraphError("Telegraph getPage timed out")
        except Exception as e:
            logger.error("Telegraph getPage request failed: %s", e)
            raise TelegraphError(f"Telegraph getPage request failed: {e}")

        if not data.get("ok"):
            error = data.get("error", "unknown error")
            logger.error("Telegraph getPage error: %s", error)
            raise TelegraphError(f"Telegraph getPage failed: {error}")

        result = data.get("result") or {}
        links = self._extract_links(result.get("content") or [])
        return {"title": result.get("title", ""), "links": links}

    @classmethod
    def _extract_links(cls, nodes: list, links: list[str] | None = None) -> list[str]:
        """Recursively collect ``href`` values from a Telegraph Node array."""
        if links is None:
            links = []
        for node in nodes:
            if isinstance(node, str):
                continue
            if isinstance(node, dict):
                attrs = node.get("attrs") or {}
                href = attrs.get("href")
                if href:
                    links.append(href)
                children = node.get("children")
                if children:
                    cls._extract_links(children, links)
        return links

    async def edit_page(self, path: str, title: str, content_html: str) -> str:
        """Edit an existing page (created by the same account).

        Args:
            path: The page path from its URL (the part after telegra.ph/).
            title: New page title.
            content_html: New page content as an HTML fragment.

        Returns:
            The updated page URL.

        Raises:
            TelegraphError: if the API rejects the request.
        """
        token = await self._load_token()

        if len(content_html.encode("utf-8")) > _TELEGRAPH_CONTENT_LIMIT:
            content_html = self._truncate_html(content_html, _TELEGRAPH_CONTENT_LIMIT)

        nodes = self._html_to_nodes(content_html)

        params = {
            "access_token": token,
            "path": path,
            "title": title,
            "author_name": settings.telegraph_author_name,
            "content": json.dumps(nodes),
            "return_content": False,
        }
        data = await self._api_call("editPage", params=params)
        url = data.get("url", "")
        if not url:
            raise TelegraphError("Telegraph editPage returned no URL")
        logger.info("Telegraph page edited: %s", url)
        return url

    # ── Low level ─────────────────────────────────────────────

    async def _api_call(self, method: str, params: dict[str, Any]) -> dict:
        """Call a Telegraph API method (form-encoded POST) and return 'result'."""
        url = f"{self._base}/{method}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, data=params)
                data = resp.json()
        except httpx.TimeoutException:
            logger.error("Telegraph %s timed out", method)
            raise TelegraphError(f"Telegraph {method} timed out")
        except Exception as e:
            logger.error("Telegraph %s request failed: %s", method, e)
            raise TelegraphError(f"Telegraph {method} request failed: {e}")

        if not data.get("ok"):
            error = data.get("error", "unknown error")
            logger.error("Telegraph %s error: %s", method, error)
            raise TelegraphError(f"Telegraph {method} failed: {error}")

        return data.get("result") or {}

    # ── HTML → Telegraph nodes ────────────────────────────────

    @classmethod
    def _html_to_nodes(cls, content_html: str) -> list[dict]:
        """Convert an HTML fragment into a Telegraph Node array."""
        soup = BeautifulSoup(content_html, "html.parser")
        nodes: list[dict] = []
        for element in soup.children:
            nodes.extend(cls._element_to_nodes(element))
        return nodes

    @classmethod
    def _element_to_nodes(cls, element: Any) -> list[dict]:
        """Convert one HTML element to zero or more Telegraph nodes."""
        if element.name is None:
            # Plain text node
            text = str(element).strip()
            return [text] if text else []

        if element.name not in _TELEGRAPH_TAGS:
            # Unsupported tag — hoist its children
            result: list[dict] = []
            for child in element.children:
                result.extend(cls._element_to_nodes(child))
            return result

        node: dict[str, Any] = {"tag": element.name}
        if element.name == "a":
            href = element.get("href")
            if href:
                node["attrs"] = {"href": href}
        elif element.name == "img":
            src = element.get("src")
            if src:
                node["attrs"] = {"src": src}

        children: list[Any] = []
        for child in element.children:
            children.extend(cls._element_to_nodes(child))
        if children:
            node["children"] = children
        return [node]

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _truncate_html(content: str, limit_bytes: int) -> str:
        """Naively truncate HTML content to fit the Telegraph byte limit."""
        encoded = content.encode("utf-8")
        if len(encoded) <= limit_bytes:
            return content
        # Cut at the last paragraph boundary below the limit
        cut = content[:limit_bytes]
        boundary = cut.rfind("</p>")
        if boundary > 0:
            return cut[: boundary + 4] + "<p>…</p>"
        return cut[:limit_bytes] + "…"


def esc(text: str | None) -> str:
    """Escape text for safe inclusion in Telegraph HTML content."""
    return html.escape(str(text or ""))
