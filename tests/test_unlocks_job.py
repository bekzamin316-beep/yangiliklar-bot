"""Unit tests for the weekly token unlocks scheduler job (retry logic, no network)."""

import pytest

import src.scheduler.jobs as jobs
from tests.test_calendar_job import FakePublisher


class GoodUnlocksService:
    async def build_weekly_message_with_chart_async(self) -> tuple[list[str], list[bytes]]:
        return ["🔓 top unlocks"], []


class ChartUnlocksService:
    async def build_weekly_message_with_chart_async(self) -> tuple[list[str], list[bytes]]:
        return ["🔓 top unlocks", "detail"], [b"PNG-DATA"]


class MultiChartUnlocksService:
    async def build_weekly_message_with_chart_async(self) -> tuple[list[str], list[bytes]]:
        return ["🔓 top unlocks 1-5", "🔓 top unlocks 6-10"], [b"PNG-1", b"PNG-2"]


class EmptyUnlocksService:
    async def build_weekly_message_with_chart_async(self) -> tuple[list[str], list[bytes]]:
        return [], []


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setattr(jobs, "_CALENDAR_RETRY_SECONDS", 0)


async def test_publishes_unlocks(monkeypatch):
    monkeypatch.setattr(
        "src.unlocks_service.service.TokenUnlocksService", GoodUnlocksService
    )
    pub = FakePublisher()
    await jobs.send_token_unlocks(pub)
    assert pub.published == ["🔓 top unlocks"]
    assert "yuborildi" in pub.notifications[0]


async def test_publishes_photo_with_caption_then_remaining_text(monkeypatch):
    monkeypatch.setattr(
        "src.unlocks_service.service.TokenUnlocksService", ChartUnlocksService
    )
    pub = FakePublisher()
    await jobs.send_token_unlocks(pub)
    assert pub.photos == [(b"PNG-DATA", "🔓 top unlocks")]
    assert pub.published == []
    assert "yuborildi" in pub.notifications[0]


async def test_publishes_multiple_photos_each_with_own_caption(monkeypatch):
    monkeypatch.setattr(
        "src.unlocks_service.service.TokenUnlocksService", MultiChartUnlocksService
    )
    pub = FakePublisher()
    await jobs.send_token_unlocks(pub)
    assert pub.photos == [
        (b"PNG-1", "🔓 top unlocks 1-5"),
        (b"PNG-2", "🔓 top unlocks 6-10"),
    ]
    assert pub.published == []
    assert "yuborildi" in pub.notifications[0]


async def test_gives_up_and_notifies_admin(monkeypatch):
    monkeypatch.setattr(
        "src.unlocks_service.service.TokenUnlocksService", EmptyUnlocksService
    )
    pub = FakePublisher()
    await jobs.send_token_unlocks(pub)
    assert pub.published == []
    assert "yuborilmadi" in pub.notifications[0]
