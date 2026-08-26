"""Unit tests for the weekly economic calendar service (no network)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.calendar_service.service import EconomicCalendarService, _impact_rank
from src.core.config import settings

TZ = ZoneInfo(settings.digest_timezone)


def _ev(date_iso: str, title: str = "CPI y/y", country: str = "USD",
        impact: str = "High", forecast: str = "3.3%", previous: str = "3.8%") -> dict:
    when = datetime.fromisoformat(date_iso).astimezone(TZ)
    return {"date": date_iso, "title": title, "country": country,
            "impact": impact, "forecast": forecast, "previous": previous,
            "_when": when}


@pytest.fixture
def svc() -> EconomicCalendarService:
    return EconomicCalendarService()


class TestImpactRank:
    def test_known_values(self):
        assert _impact_rank("Low") == 0
        assert _impact_rank("Medium") == 1
        assert _impact_rank("High") == 2

    def test_unknown_defaults_to_low(self):
        assert _impact_rank("") == 0
        assert _impact_rank("whatever") == 0


class TestFilterUpcomingWeek:
    def test_sunday_selects_next_monday_onwards(self, svc):
        # Sunday 2026-08-30 evening → upcoming week is Aug 31 – Sep 6
        now = datetime(2026, 8, 30, 20, 0, tzinfo=TZ)
        events = [
            _ev("2026-08-28T17:30:00+05:00"),  # old week — dropped
            _ev("2026-08-31T17:30:00+05:00"),  # next Mon — kept
            _ev("2026-09-04T19:00:00+05:00"),  # next Fri — kept
            _ev("2026-09-06T21:15:00+05:00"),  # next Sun — kept
            _ev("2026-09-07T06:30:00+05:00"),  # week after — dropped
        ]
        kept = svc._filter_upcoming_week(events, now=now)
        assert [e["title"] for e in kept] == ["CPI y/y"] * 3

    def test_midweek_selects_following_week(self, svc):
        now = datetime(2026, 8, 25, 12, 0, tzinfo=TZ)  # Tuesday
        events = [
            _ev("2026-08-26T17:30:00+05:00"),  # this week — dropped
            _ev("2026-08-31T06:30:00+05:00"),  # next Mon — kept
        ]
        assert len(svc._filter_upcoming_week(events, now=now)) == 1


class TestFormatting:
    def test_event_line_with_extras(self, svc):
        ev = _ev("2026-08-25T17:15:00-04:00")
        line = svc._format_event_line(ev, "ADP Employment")
        assert line.startswith("🇺🇸 <b>AQSH</b> — ADP Employment — <b>")
        assert "kutilmoqda: 3.3%" in line
        assert "oldingi: 3.8%" in line

    def test_all_country_maps_to_global(self, svc):
        ev = _ev("2026-08-27T21:15:00+05:00", country="ALL", forecast="", previous="")
        line = svc._format_event_line(ev, "Jackson Hole Symposium")
        assert line.startswith("🌐 <b>Global</b>")
        assert "kutilmoqda" not in line and "oldingi" not in line

    def test_day_header_uzbek(self, svc):
        ev = _ev("2026-08-24T10:00:00+05:00")  # Monday
        assert svc._day_header(ev["_when"]) == "<b>Dushanba, 24 avgust</b>"

    def test_header_range_same_month(self, svc):
        events = [_ev("2026-08-31T10:00:00+05:00"), _ev("2026-09-04T10:00:00+05:00")]
        header = svc._header(events)
        assert header.startswith("🗓 <b>KALENDAR — ")
        assert "31 avgust" in header or "AVGUST" in header.upper()


class TestSplitMessage:
    def test_no_split_under_limit(self, svc):
        parts = svc._split_message(["a" * 100, "b" * 100])
        assert len(parts) == 1

    def test_splits_over_limit_with_continuation_prefix(self, svc):
        blocks = [f"block{i} " + "x" * 1500 for i in range(4)]
        parts = svc._split_message(blocks, limit=2000)
        assert len(parts) >= 2
        assert all(len(p) <= 2100 for p in parts)
        assert parts[1].startswith("(davom1)")
