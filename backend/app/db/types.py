"""Portable column types (work unchanged on SQLite and PostgreSQL)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """``DateTime(timezone=True)`` that always hands back timezone-aware UTC values.

    SQLite drops tzinfo; values are normalised to UTC on the way in and re-tagged as UTC on the way out.
    PostgreSQL (timestamptz) already returns aware values, which are converted to UTC as well.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:  # naive values are taken to be UTC
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class UuidList(TypeDecorator):
    """list[UUID] stored as a JSON array of strings."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: list[UUID] | None, dialect: Any):
        return None if value is None else [str(v) for v in value]

    def process_result_value(self, value: list[str] | None, dialect: Any):
        return None if value is None else [UUID(v) for v in value]


class UuidKeyedNames(TypeDecorator):
    """dict[UUID, str] stored as a JSON object."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: dict[UUID, str] | None, dialect: Any):
        return None if value is None else {str(k): v for k, v in value.items()}

    def process_result_value(self, value: dict[str, str] | None, dialect: Any):
        return None if value is None else {UUID(k): v for k, v in value.items()}


class Standings(TypeDecorator):
    """Final standings: list of dicts whose ``restaurant_id`` is a UUID in Python and a string in JSON."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: list[dict] | None, dialect: Any):
        return None if value is None else [{**s, "restaurant_id": str(s["restaurant_id"])} for s in value]

    def process_result_value(self, value: list[dict] | None, dialect: Any):
        return None if value is None else [{**s, "restaurant_id": UUID(s["restaurant_id"])} for s in value]
