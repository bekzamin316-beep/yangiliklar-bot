"""Weekly economic calendar — fetches ForexFactory data and builds an Uzbek channel post.

The post format mirrors a classic trader calendar:

    🗓 KALENDAR — 24–28 AVGUST 2026

    <b>Dushanba, 24 avgust</b>
    🇺🇸 AQSH — ADP Employment — 17:30
    ...

Events are grouped by local day (Asia/Tashkent), filtered by impact, and event
titles are translated to Uzbek via the shared TranslationService when an AI key
is configured (English fallback otherwise).
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings

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

# ForexFactory currency code → (flag emoji, Uzbek country name)
_COUNTRIES = {
    "USD": ("🇺🇸", "AQSH"),
    "EUR": ("🇪🇺", "Yevro hududi"),
    "GBP": ("🇬🇧", "Britaniya"),
    "JPY": ("🇯🇵", "Yaponiya"),
    "AUD": ("🇦🇺", "Avstraliya"),
    "CAD": ("🇨🇦", "Kanada"),
    "CHF": ("🇨🇭", "Shveysariya"),
    "NZD": ("🇳🇿", "Yangi Zelandiya"),
    "CNY": ("🇨🇳", "Xitoy"),
    "RUB": ("🇷🇺", "Rossiya"),
    "ALL": ("🌐", "Global"),
}

_IMPACT_RANK = {"low": 0, "medium": 1, "high": 2}


def _impact_rank(impact: str) -> int:
    return _IMPACT_RANK.get((impact or "").strip().lower(), 0)


class EconomicCalendarService:
    """Fetches the weekly economic calendar and formats it for Telegram."""

    def __init__(self) -> None:
        self._translator = None
        self._translation_cache: dict[str, str] = {}

    # ── Data fetching ─────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=10, min=10, max=60),
        reraise=True,
    )
    async def fetch_events(self) -> list[dict]:
        """Fetch this week's events from the configured JSON source."""
        url = settings.calendar_api_url
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CryptoNewsBot/1.0)"}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            events = resp.json()

        if not isinstance(events, list):
            raise ValueError(f"Unexpected calendar payload type: {type(events)}")
        logger.info("Calendar: fetched %d raw events from %s", len(events), url)
        return events

    def _filter_events(self, events: list[dict]) -> list[dict]:
        """Keep only events meeting the minimum impact, with a parseable date."""
        min_rank = _impact_rank(settings.calendar_min_impact)
        kept: list[dict] = []
        for ev in events:
            try:
                when = datetime.fromisoformat(ev["date"])
            except Exception:
                continue
            if _impact_rank(ev.get("impact", "")) < min_rank:
                continue
            kept.append({**ev, "_when": when.astimezone(LOCAL_TZ)})
        kept.sort(key=lambda e: e["_when"])
        logger.info("Calendar: %d events after impact>=%s filter", len(kept), settings.calendar_min_impact)
        return kept

    def _filter_upcoming_week(self, events: list[dict], *, now: datetime | None = None) -> list[dict]:
        """Keep only events in the upcoming Mon–Sun window relative to ``now``.

        The Sunday-evening post must show NEXT week, but the ForexFactory
        ``thisweek`` feed may still contain the ending week for part of the
        weekend — filtering by window makes that flip harmless.
        """
        ref = now or datetime.now(LOCAL_TZ)
        days_ahead = (7 - ref.weekday()) % 7 or 7  # next Monday (tomorrow on Sunday)
        week_start = (ref + timedelta(days=days_ahead)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=7)
        kept = [e for e in events if week_start <= e["_when"] < week_end]
        logger.info(
            "Calendar: %d events in upcoming week %s..%s",
            len(kept), week_start.date(), (week_end - timedelta(days=1)).date(),
        )
        return kept

    # ── Translation ───────────────────────────────────────────

    async def _translate_titles(self, titles: list[str]) -> dict[str, str]:
        """Translate unique event titles to Uzbek (cached). English on failure."""
        todo = [t for t in titles if t not in self._translation_cache]
        if not todo:
            return {t: self._translation_cache[t] for t in titles}

        translator = await self._get_translator()
        if translator is None:
            return {}

        sem = asyncio.Semaphore(3)

        async def one(title: str) -> None:
            async with sem:
                try:
                    result = await translator.translate_to_uzbek(title)
                    self._translation_cache[title] = result or title
                except Exception as e:
                    logger.warning("Calendar title translation failed (%s): %s", title[:40], e)
                    self._translation_cache[title] = title

        await asyncio.gather(*(one(t) for t in todo))
        return {t: self._translation_cache[t] for t in titles}

    async def _get_translator(self):
        """Lazily build a TranslationService; None when no provider has credentials."""
        if self._translator is not None:
            return self._translator
        try:
            from src.ai_service.translation import TranslationService
            service = TranslationService()
            if not service.providers:
                logger.info("Calendar: no translation providers configured — keeping original titles")
                self._translator = False
                return None
            self._translator = service
            return service
        except Exception as e:
            logger.warning("Calendar translator init failed: %s", e)
            self._translator = False
            return None

    # ── Formatting ────────────────────────────────────────────

    @staticmethod
    def _fmt_hm(when: datetime) -> str:
        return when.strftime("%H:%M")

    def _format_event_line(self, ev: dict, translated_title: str) -> str:
        flag, country = _COUNTRIES.get(
            (ev.get("country") or "").upper(), ("🌐", (ev.get("country") or "?").upper())
        )
        parts = [f"{flag} <b>{country}</b> — {translated_title}"]
        extras = []
        if ev.get("forecast"):
            extras.append(f"kutilmoqda: {ev['forecast']}")
        if ev.get("previous"):
            extras.append(f"oldingi: {ev['previous']}")
        line = f"{parts[0]} — <b>{self._fmt_hm(ev['_when'])}</b>"
        if extras:
            line += f" ({', '.join(extras)})"
        return line

    def _day_header(self, when: datetime) -> str:
        weekday = _UZ_WEEKDAYS[when.weekday()]
        return f"<b>{weekday}, {when.day} {_UZ_MONTHS[when.month - 1]}</b>"

    def _header(self, events: list[dict]) -> str:
        first_day = min(e["_when"] for e in events)
        last_day = max(e["_when"] for e in events)
        if first_day.year == last_day.year:
            range_str = (
                f"{first_day.day}–{last_day.day} {_UZ_MONTHS[first_day.month - 1].upper()} {first_day.year}"
                if first_day.month == last_day.month
                else f"{first_day.day} {_UZ_MONTHS[first_day.month - 1]} – "
                     f"{last_day.day} {_UZ_MONTHS[last_day.month - 1].upper()} {last_day.year}"
            )
        else:
            range_str = f"{first_day.date()} – {last_day.date()}"
        return f"🗓 <b>KALENDAR — {range_str}</b>"

    def _split_message(self, blocks: list[str], limit: int = 3900) -> list[str]:
        """Split day-blocks into chunks under the Telegram length limit."""
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

    async def build_weekly_message(self) -> list[str]:
        """Build one or more HTML-formatted channel posts for next week's calendar."""
        raw = await self.fetch_events()
        events = self._filter_events(raw)
        if not events:
            logger.warning("Calendar: no events match the impact filter — nothing to send")
            return []
        events = self._filter_upcoming_week(events)
        if not events:
            logger.warning("Calendar: feed does not contain next week yet — nothing to send")
            return []

        translations = await self._translate_titles([e.get("title", "") for e in events])

        by_day: dict[str, list[dict]] = defaultdict(list)
        for ev in events:
            by_day[ev["_when"].date().isoformat()].append(ev)

        high_impact = [e for e in events if _impact_rank(e.get("impact", "")) >= 2]

        blocks = [self._header(events)]
        for day_key in sorted(by_day):
            day_events = by_day[day_key]
            blocks.append(self._day_header(day_events[0]["_when"]))
            for ev in day_events:
                title = ev.get("title", "")
                translated = translations.get(title, title)
                blocks.append(self._format_event_line(ev, translated))

        if high_impact:
            highlights = ", ".join(
                translations.get(e.get("title", ""), e.get("title", ""))
                for e in high_impact[:8]
            )
            blocks.append(f"🔥 <b>Kripto bozori uchun eng muhimi:</b> {highlights}")

        return self._split_message(blocks)
