"""Injectable clock so tests (and the scheduler) control 'now'."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Request


class Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock(Clock):
    def __init__(self, start: datetime):
        assert start.tzinfo is not None
        self._now = start.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._now

    def set(self, value: datetime) -> None:
        self._now = value.astimezone(timezone.utc)

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)


def get_clock(request: Request) -> Clock:
    """FastAPI dependency; override via app.dependency_overrides[get_clock] or app.state.clock."""
    return request.app.state.clock
