"""Unit tests for the weekly calendar scheduler job (retry logic, no network)."""

import pytest

import src.scheduler.jobs as jobs


class FakePublisher:
    def __init__(self):
        self.published: list[str] = []
        self.notifications: list[str] = []
        self.photos: list[tuple[bytes, str]] = []

    async def publish_digest(self, text: str) -> bool:
        self.published.append(text)
        return True

    async def publish_photo(self, photo_bytes: bytes, caption: str = "") -> bool:
        self.photos.append((photo_bytes, caption))
        return True

    async def send_admin_notification(self, text: str) -> None:
        self.notifications.append(text)


class FlakyService:
    """Returns [] for the first N calls, then a message."""

    fail_times = 2

    def __init__(self):
        self.calls = 0

    async def build_weekly_message(self) -> list[str]:
        self.calls += 1
        if self.calls <= self.fail_times:
            return []
        return ["🗓 calendar"]


class BrokenThenGoodService(FlakyService):
    def __init__(self):
        super().__init__()
        self.fail_times = 0

    async def build_weekly_message(self) -> list[str]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("429 Too Many Requests")
        return ["🗓 calendar"]


class AlwaysEmptyService:
    async def build_weekly_message(self) -> list[str]:
        return []


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setattr(jobs, "_CALENDAR_RETRY_SECONDS", 0)


def _patch_service(monkeypatch, svc_cls):
    monkeypatch.setattr(
        "src.calendar_service.service.EconomicCalendarService", svc_cls
    )


async def test_publishes_after_empty_results(monkeypatch):
    _patch_service(monkeypatch, FlakyService)
    pub = FakePublisher()
    await jobs.send_economic_calendar(pub)
    assert pub.published == ["🗓 calendar"]
    assert "yuborildi" in pub.notifications[0]


async def test_recovers_from_exception(monkeypatch):
    _patch_service(monkeypatch, BrokenThenGoodService)
    pub = FakePublisher()
    await jobs.send_economic_calendar(pub)
    assert pub.published == ["🗓 calendar"]


async def test_gives_up_and_notifies_admin(monkeypatch):
    _patch_service(monkeypatch, AlwaysEmptyService)
    pub = FakePublisher()
    await jobs.send_economic_calendar(pub)
    assert pub.published == []
    assert len(pub.notifications) == 1
    assert "yuborilmadi" in pub.notifications[0]


async def test_stops_sending_on_first_failure(monkeypatch):
    _patch_service(monkeypatch, FlakyService)

    class FailAfterFirst(FakePublisher):
        async def publish_digest(self, text: str) -> bool:
            if self.published:
                return False
            return await super().publish_digest(text) and True

    pub = FailAfterFirst()
    await jobs.send_economic_calendar(pub)
    assert len(pub.published) == 1
