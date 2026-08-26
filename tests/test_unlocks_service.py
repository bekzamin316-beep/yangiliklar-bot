"""Unit tests for the weekly token unlocks service (no network)."""

from datetime import datetime

import pytest

from src.unlocks_service.service import TokenUnlocksService, _fmt_usd

TZ_HOURS = 5  # Asia/Tashkent is UTC+5


def _item(symbol: str, name: str, iso_date: str, usd: float,
          allocations: list[str] | None = None) -> dict:
    when = datetime.fromisoformat(iso_date)
    ts_ms = int(when.timestamp() * 1000)
    detail = [{"allocationName": a, "tokenAmountUsd": usd / max(len(allocations), 1)}
              for a in (allocations or [])]
    return {
        "symbol": symbol, "name": name,
        "nextUnlocked": {"date": ts_ms, "tokenAmountUsd": usd, "tokenAmountPercentage": 1.5},
        "nextUnlockedDetail": detail,
    }


@pytest.fixture
def svc() -> TokenUnlocksService:
    return TokenUnlocksService()


class TestFmtUsd:
    def test_millions(self):
        assert _fmt_usd(12_400_000) == "12,40 mln $"

    def test_thousands(self):
        assert _fmt_usd(850_000) == "850 ming $"

    def test_billions(self):
        assert _fmt_usd(2_500_000_000) == "2,50 mlrd $"

    def test_zero_safe(self):
        assert _fmt_usd(None) == "0 ming $"


class TestFilterUpcomingWeek:
    def test_selects_next_week_sorted_by_usd_desc(self, svc):
        now = datetime(2026, 8, 25, 12, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Tashkent"))
        items = [
            _item("AAA", "Alpha", "2026-08-26T10:00:00+05:00", 5_000_000),   # this week — dropped
            _item("BBB", "Beta", "2026-09-01T15:00:00+05:00", 1_000_000),    # next week
            _item("CCC", "Gamma", "2026-09-02T10:00:00+05:00", 9_000_000),   # next week
            _item("DDD", "Delta", "2026-09-08T10:00:00+05:00", 99_000_000),  # week after — dropped
        ]
        kept = svc._filter_upcoming_week(items, now=now)
        assert [e["symbol"] for e in kept] == ["CCC", "BBB"]

    def test_skips_items_without_unlock(self, svc):
        now = datetime(2026, 8, 30, 20, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Tashkent"))
        items = [{"symbol": "NOPE"}, _item("OKK", "Okki", "2026-09-01T10:00:00+05:00", 100)]
        assert len(svc._filter_upcoming_week(items, now=now)) == 1


class TestFormatting:
    def test_full_message_structure(self, svc):
        now = datetime(2026, 8, 30, 20, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Tashkent"))
        items = [
            _item("ARB", "Arbitrum", "2026-09-01T15:00:00+05:00", 12_400_000, ["Investors", "Team"]),
            _item("OP", "Optimism", "2026-08-31T10:00:00+05:00", 4_500_000, ["Core Developers"]),
            _item("SMOL", "Smallcoin", "2026-09-03T08:00:00+05:00", 300_000),
        ]
        parts = svc.build_weekly_message_sync_items(items, now=now)
        assert len(parts) == 1
        text = parts[0]
        assert "🔓 <b>TOP-3 QULFDAN OCHILADIGAN TOKENLAR" in text
        assert "31 AVGUST – 6 SENTABR 2026" in text
        # sorted by USD desc → ARB first with 🥇
        pos_arb, pos_op, pos_smol = text.index("ARB"), text.index("OP<"), text.index("SMOL")
        assert pos_arb < pos_op < pos_smol
        assert "🥇" in text and "🥈" in text
        assert "12,40 mln $" in text
        assert "Klaster: Investors, Team" in text
        # totals include all three events + source line
        assert "Jami haftalik unlock" in text
        assert "CoinMarketCap" in text

    def test_top_n_limit(self, svc):
        now = datetime(2026, 8, 30, 20, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Tashkent"))
        items = [_item(f"T{i:02d}", f"Token{i}", f"2026-09-0{(i % 7) + 1}T10:00:00+05:00", i * 1e6)
                 for i in range(1, 16)]
        parts = svc.build_weekly_message_sync_items(items, now=now)
        text = parts[0]
        assert "TOP-10" in text
        assert "15." not in text.split("\n\n")[-3]  # ranks capped at 10

    def test_empty_week_returns_empty(self, svc):
        now = datetime(2026, 8, 25, 12, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Tashkent"))
        items = [_item("XXX", "Xoxo", "2026-08-27T10:00:00+05:00", 1_000)]
        assert svc.build_weekly_message_sync_items(items, now=now) == []
