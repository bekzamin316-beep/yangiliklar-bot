"""Unit tests for the weekly token unlocks scheduler job (retry logic, no network)."""

import pytest

import src.scheduler.jobs as jobs
from tests.test_calendar_job import FakePublisher


class GoodUnlocksService:
    async def build_weekly_message(self) -> list[str]:
        return ["🔓 top unlocks"]


class EmptyUnlocksService:
    async def build_weekly_message(self) -> list[str]:
        return []


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


async def test_gives_up_and_notifies_admin(monkeypatch):
    monkeypatch.setattr(
        "src.unlocks_service.service.TokenUnlocksService", EmptyUnlocksService
    )
    pub = FakePublisher()
    await jobs.send_token_unlocks(pub)
    assert pub.published == []
    assert "yuborilmadi" in pub.notifications[0]
