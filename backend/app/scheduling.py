"""Team-local scheduling helpers (DST safe via zoneinfo)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

WEEKDAYS = [1, 2, 3, 4, 5]


def parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def local_date(now: datetime, tz: str) -> date:
    return now.astimezone(ZoneInfo(tz)).date()


def is_poll_day(d: date) -> bool:
    return d.isoweekday() in WEEKDAYS


def next_poll_day(d: date) -> date:
    """First poll day strictly after d."""
    d += timedelta(days=1)
    while not is_poll_day(d):
        d += timedelta(days=1)
    return d


def window(d: date, tz: str, open_time: str, close_time: str) -> tuple[datetime, datetime]:
    """UTC instants of local open/close on local date d."""
    z = ZoneInfo(tz)
    o = datetime.combine(d, parse_hhmm(open_time), tzinfo=z).astimezone(timezone.utc)
    c = datetime.combine(d, parse_hhmm(close_time), tzinfo=z).astimezone(timezone.utc)
    return o, c
