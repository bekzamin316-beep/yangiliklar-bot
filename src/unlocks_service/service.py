"""Weekly top token unlocks — fetches CoinMarketCap data and builds an Uzbek channel post.

Post format:

    🔓 TOP-10 QULFDAN OCHILADIGAN TOKENLAR — 31 AVGUST – 6 SENTABR 2026

    🥇 <b>ARB</b> (Arbitrum) — <b>12,4 mln $</b> — Seshanba, 1 sentyabr, 15:00
       Klaster: Investors, Team
    ...

Events come from the public CoinMarketCap data-api listing endpoint (no key),
are filtered to the upcoming Monday–Sunday window (Asia/Tashkent), ranked by
USD value, and the top ``unlocks_top_n`` are published.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.unlocks_service.chart import render_unlocks_charts, _fmt_tokens, fetch_token_logos

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo(settings.digest_timezone)

_UZ_WEEKDAYS = {
    0: "Dushanba", 1: "Seshanba", 2: "Chorshanba",
    3: "Payshanba", 4: "Juma", 5: "Shanba", 6: "Yakshanba",
}
_UZ_MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]

_RANK_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}


def _fmt_usd(value: float) -> str:
    """Format a USD amount the Uzbek way: 1,27 mln $ / 850 ming $."""
    v = float(value or 0)
    if abs(v) >= 1e9:
        text, unit = f"{v / 1e9:.2f}", "mlrd $"
    elif abs(v) >= 1e6:
        text, unit = f"{v / 1e6:.2f}", "mln $"
    else:
        text, unit = f"{v / 1e3:.0f}", "ming $"
    return f"{text.replace('.', ',')} {unit}"


def _week_range_str(start: datetime, end: datetime) -> str:
    def day_month(dt: datetime) -> str:
        return f"{dt.day} {_UZ_MONTHS[dt.month - 1]}"

    if start.month == end.month:
        return f"{start.day}–{end.day} {_UZ_MONTHS[start.month - 1].upper()} {start.year}"
    return (
        f"{day_month(start).upper()} – {day_month(end).upper()} {end.year}"
    )


class TokenUnlocksService:
    """Fetches upcoming token unlocks and formats a weekly top-list."""

    DEFAULT_API_URL = "https://api.coinmarketcap.com/data-api/v3/token-unlock/listing"

    # ── Data fetching ─────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=10, min=10, max=60),
        reraise=True,
    )
    async def _fetch_page(self, client: httpx.AsyncClient, page: int) -> dict:
        url = getattr(settings, "unlocks_api_url", None) or self.DEFAULT_API_URL
        resp = await client.get(url, params={
            "pageNum": page,
            "pageSize": 100,
            "enableSmallUnlocks": "false",
        })
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected unlocks payload type: {type(payload)}")
        return data

    async def fetch_events(self) -> list[dict]:
        """Fetch upcoming unlock listings.

        The public endpoint returns the ~100 nearest events and currently
        ignores ``pageNum``/``pageSize`` — identical consecutive pages are
        detected via token ids and dropped.
        """
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CryptoNewsBot/1.0)"}
        max_pages = getattr(settings, "unlocks_max_pages", 6)
        items: list[dict] = []
        seen_ids: set[int] = set()
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            for page in range(1, max_pages + 1):
                data = await self._fetch_page(client, page)
                batch = data.get("tokenUnlockList") or []
                fresh = [
                    x for x in batch
                    if x.get("cryptoId") is not None and x["cryptoId"] not in seen_ids
                ]
                if not fresh:
                    logger.info("Unlocks: page %d adds nothing new — stopping", page)
                    break
                seen_ids.update(x["cryptoId"] for x in fresh)
                items.extend(fresh)
                total = int(data.get("totalCount") or 0)
                logger.info(
                    "Unlocks: page %d/%d — %d entries (total=%d)",
                    page, max_pages, len(items), total,
                )
                if total and len(items) >= total:
                    break
                await asyncio.sleep(0.4)
        return items

    # ── Filtering ─────────────────────────────────────────────

    def _filter_upcoming_week(
        self, items: list[dict], *, now: datetime | None = None,
    ) -> list[dict]:
        """Keep events whose unlock date falls in the upcoming Mon–Sun window."""
        ref = now or datetime.now(LOCAL_TZ)
        days_ahead = (7 - ref.weekday()) % 7 or 7  # next Monday (tomorrow on Sunday)
        week_start = (ref + timedelta(days=days_ahead)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        week_end = week_start + timedelta(days=7)

        kept: list[dict] = []
        for it in items:
            nu = it.get("nextUnlocked") or {}
            ts = nu.get("date")
            if not ts:
                continue
            when = datetime.fromtimestamp(ts / 1000, tz=LOCAL_TZ)
            if week_start <= when < week_end:
                kept.append({**it, "_when": when})
        def _usd(ev: dict) -> float:
            return (ev.get("nextUnlocked") or {}).get("tokenAmountUsd") or 0.0

        kept.sort(key=lambda e: -_usd(e))
        logger.info(
            "Unlocks: %d events in upcoming week %s..%s",
            len(kept), week_start.date(), (week_end - timedelta(days=1)).date(),
        )
        return kept

    # ── Formatting ────────────────────────────────────────────

    def _rank_label(self, rank: int) -> str:
        prefix = _RANK_EMOJI.get(rank, f"{rank}.")
        return f"{prefix} "

    def _event_line(self, rank: int, ev: dict) -> str:
        nu = ev.get("nextUnlocked") or {}
        usd = _fmt_usd(nu.get("tokenAmountUsd"))
        pct = nu.get("tokenAmountPercentage")
        when = ev["_when"]
        weekday = _UZ_WEEKDAYS[when.weekday()]
        date_str = f"{weekday}, {when.day} {_UZ_MONTHS[when.month - 1]}"
        line = (
            f"{self._rank_label(rank)}<b>{ev.get('symbol', '?')}</b>"
            f" ({ev.get('name', '')}) — <b>{usd}</b> — {date_str}, {when.strftime('%H:%M')}"
        )
        extra: list[str] = []
        if pct is not None:
            extra.append(f"taqsimotning {str(pct).replace('.', ',')}% i ochiladi")
        locked = ev.get("tokenLockedAmount")
        if locked:
            extra.append(f"qulfdan qoldi: {_fmt_tokens(locked)} token")
        if extra:
            line += "\n     " + " · ".join(extra)
        details = ev.get("nextUnlockedDetail") or []
        names = [
            (d.get("allocationName") or "").strip() for d in details
            if d.get("allocationName")
        ]
        # Normalize ALL-CAPS cluster names coming from the source
        names = [n.title() if n.isupper() else n for n in names]
        unique = list(dict.fromkeys(n for n in names if n))
        if unique:
            shown = ", ".join(unique[:3])
            if len(unique) > 3:
                shown += " va boshqalar"
            line += f"\n     Klaster: {shown}"
        return line

    def _split_message(self, blocks: list[str], limit: int = 3900) -> list[str]:
        messages: list[str] = []
        current: list[str] = []
        size = 0
        for block in blocks:
            blen = len(block)
            if current and size + blen > limit:
                messages.append("\n\n".join(current))
                current, size = [], 0
            current.append(block)
            size += blen + 2
        if current:
            messages.append("\n\n".join(current))
        for i, msg in enumerate(messages[1:], 1):
            messages[i] = f"(davom{i})\n\n{msg}"
        return messages

    # ── Public API ────────────────────────────────────────────

    def build_weekly_message_sync_items(self, items: list[dict], *, now: datetime | None = None) -> list[str]:
        """Format an already-fetched listing (used by tests and the main path)."""
        events = self._filter_upcoming_week(items, now=now)
        if not events:
            logger.warning("Unlocks: no events in the upcoming week — nothing to send")
            return []

        top_n = getattr(settings, "unlocks_top_n", 10)
        ref = now or datetime.now(LOCAL_TZ)
        days_ahead = (7 - ref.weekday()) % 7 or 7
        week_start = (ref + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        blocks = [
            f"🔓 <b>TOP-{min(top_n, len(events))} QULFDAN OCHILADIGAN TOKENLAR — "
            f"{_week_range_str(week_start, week_end - timedelta(days=1))}</b>",
        ]
        for rank, ev in enumerate(events[:top_n], 1):
            blocks.append(self._event_line(rank, ev))

        total_usd = sum(
            (e.get("nextUnlocked") or {}).get("tokenAmountUsd") or 0 for e in events
        )
        blocks.append(f"💰 <b>Jami haftalik unlock:</b> ≈{_fmt_usd(total_usd)}")
        blocks.append("🔗 Manba: CoinMarketCap")
        return self._split_message(blocks)

    def build_weekly_message_with_chart(
        self, items: list[dict], *, now: datetime | None = None,
        logos: dict | None = None,
    ) -> tuple[list[str], list[bytes]]:
        """Build message parts plus PNG chart images of the top unlocks.

        Returns ``(parts, chart_images)``; ``chart_images`` is an empty list
        when there are no events or rendering fails, in which case the
        text-only fallback is used by the caller.
        """
        events = self._filter_upcoming_week(items, now=now)
        if not events:
            logger.warning("Unlocks: no events in the upcoming week — nothing to send")
            return [], None

        top_n = getattr(settings, "unlocks_top_n", 10)
        ref = now or datetime.now(LOCAL_TZ)
        days_ahead = (7 - ref.weekday()) % 7 or 7
        week_start = (ref + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        blocks = [
            f"🔓 <b>TOP-{min(top_n, len(events))} QULFDAN OCHILADIGAN TOKENLAR — "
            f"{_week_range_str(week_start, week_end - timedelta(days=1))}</b>",
        ]
        for rank, ev in enumerate(events[:top_n], 1):
            blocks.append(self._event_line(rank, ev))

        total_usd = sum(
            (e.get("nextUnlocked") or {}).get("tokenAmountUsd") or 0 for e in events
        )
        blocks.append(f"💰 <b>Jami haftalik unlock:</b> ≈{_fmt_usd(total_usd)}")
        blocks.append("🔗 Manba: CoinMarketCap")

        chart = render_unlocks_charts(events, now=now, logos=logos)
        return self._split_message(blocks), chart

    async def build_weekly_message(self) -> list[str]:
        """Build one or more HTML posts for the upcoming week's biggest unlocks."""
        items = await self.fetch_events()
        return self.build_weekly_message_sync_items(items)

    async def build_weekly_message_with_chart_async(self) -> tuple[list[str], list[bytes]]:
        """Fetch events and build message parts plus PNG chart images."""
        items = await self.fetch_events()
        events = self._filter_upcoming_week(items)
        if not events:
            return [], []
        logos = await fetch_token_logos(events)
        return self.build_weekly_message_with_chart(items, logos=logos)
