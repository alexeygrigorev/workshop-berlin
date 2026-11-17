"""Pydantic schemas mirroring components/schemas of api/openapi.yaml (snake_case, null not omitted)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints,
                      field_validator, model_validator)
from pydantic_core import PydanticCustomError


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


Ts = Annotated[datetime, PlainSerializer(fmt_ts, return_type=str, when_used="json")]

Role = Literal["admin", "member"]
PollStatus = Literal["scheduled", "open", "closed"]
TieBreak = Literal["first_place_votes", "second_place_votes", "random_draw"]
Scope = Literal["read", "write"]

LOCAL_TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _local_time(v: str) -> str:
    if not LOCAL_TIME_RE.match(v):
        raise PydanticCustomError("invalid_format", "Use HH:MM (24h).")
    return v


def _timezone(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise PydanticCustomError("invalid_timezone", "Not a valid IANA timezone.")
    return v


def _http_url(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if v == "":
        return None
    p = urlparse(v)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise PydanticCustomError("invalid_format", "Must be an http(s) URL.")
    return v


def _blank_to_none(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


LocalTime = Annotated[str, AfterValidator(_local_time)]
TimeZoneName = Annotated[str, StringConstraints(min_length=1, max_length=64), AfterValidator(_timezone)]


class Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Strict(Base):
    """Request bodies: unknown fields are ignored (lenient clients)."""


# --- Auth / users ---------------------------------------------------------------------------
class Credentials(Strict):
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)]
    password: Annotated[str, StringConstraints(min_length=6, max_length=200)]

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.lower()
        if not EMAIL_RE.match(v):
            raise PydanticCustomError("invalid_format", "Enter a valid email address.")
        return v


class User(Base):
    id: UUID
    email: str
    display_name: str
    created_at: Ts


class UserUpdate(Strict):
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)] | None = None

    @model_validator(mode="after")
    def _nonempty(self):
        if "display_name" not in self.model_fields_set or self.display_name is None:
            raise PydanticCustomError("required", "display_name is required.")
        return self


class Session(Base):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: Ts
    user: User


class ApiTokenCreate(Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    scopes: Annotated[list[Scope], Field(min_length=1)] = ["read", "write"]
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def _unique(cls, v):
        if len(set(v)) != len(v):
            raise PydanticCustomError("duplicate_items", "Scopes must be unique.")
        return v


class ApiToken(Base):
    id: UUID
    name: str
    scopes: list[Scope]
    token_prefix: str
    created_at: Ts
    expires_at: Ts | None
    last_used_at: Ts | None


class ApiTokenWithSecret(ApiToken):
    token: str


class Health(Base):
    status: Literal["ok"] = "ok"
    version: str
    server_time: Ts


# --- Teams ----------------------------------------------------------------------------------
class TeamRef(Base):
    id: UUID
    name: str
    timezone: str


class MyTeam(Base):
    role: Role
    joined_at: Ts
    team: TeamRef


class Schedule(Base):
    open_time: str
    close_time: str
    weekdays: list[int]


class Team(Base):
    id: UUID
    name: str
    timezone: str
    office: str | None
    schedule: Schedule
    my_role: Role
    member_count: int
    created_at: Ts
    updated_at: Ts


class TeamCreate(Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    timezone: TimeZoneName
    office: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    open_time: LocalTime = "08:00"
    close_time: LocalTime = "11:30"


class TeamUpdate(Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None
    timezone: TimeZoneName | None = None
    office: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    open_time: LocalTime | None = None
    close_time: LocalTime | None = None

    @model_validator(mode="after")
    def _check(self):
        if not self.model_fields_set:
            raise PydanticCustomError("required", "Provide at least one field to update.")
        for f in ("name", "timezone", "open_time", "close_time"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise PydanticCustomError("invalid_format", f"{f} cannot be null.")
        return self


class Member(Base):
    user_id: UUID
    display_name: str
    role: Role
    joined_at: Ts


class MemberUpdate(Strict):
    role: Role


class Invite(Base):
    active: bool
    token: str | None
    url: str | None
    updated_at: Ts


class InvitePreview(Base):
    team_id: UUID
    team_name: str
    member_count: int
    already_member: bool


class JoinResult(Base):
    joined: bool
    role: Role
    team: TeamRef


# --- Restaurants ----------------------------------------------------------------------------
Name120 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Cuisine = Annotated[str, StringConstraints(max_length=80), AfterValidator(_blank_to_none)] | None
Address = Annotated[str, StringConstraints(max_length=200), AfterValidator(_blank_to_none)] | None
Url = Annotated[str, StringConstraints(max_length=500), AfterValidator(_http_url)] | None
Notes = Annotated[str, StringConstraints(max_length=500), AfterValidator(_blank_to_none)] | None


class Restaurant(Base):
    id: UUID
    team_id: UUID
    name: str
    cuisine: str | None
    address: str | None
    website_url: str | None
    map_url: str | None
    notes: str | None
    archived_at: Ts | None
    created_by: UUID | None
    created_at: Ts
    updated_at: Ts


class RestaurantCreate(Strict):
    name: Name120
    cuisine: Cuisine = None
    address: Address = None
    website_url: Url = None
    map_url: Url = None
    notes: Notes = None


class RestaurantUpdate(Strict):
    name: Name120 | None = None
    cuisine: Cuisine = None
    address: Address = None
    website_url: Url = None
    map_url: Url = None
    notes: Notes = None

    @model_validator(mode="after")
    def _check(self):
        if not self.model_fields_set:
            raise PydanticCustomError("required", "Provide at least one field to update.")
        if "name" in self.model_fields_set and self.name is None:
            raise PydanticCustomError("invalid_format", "name cannot be null.")
        return self


# --- Polls ----------------------------------------------------------------------------------
class Candidate(Base):
    id: UUID
    name: str
    archived: bool


class Standing(Base):
    restaurant_id: UUID
    name: str
    score: int
    first_count: int
    second_count: int
    third_count: int
    position: int


class Standings(Base):
    poll_id: UUID
    status: PollStatus
    final: bool
    ballot_count: int
    member_count: int
    leader_ids: list[UUID]
    winner_id: UUID | None
    no_winner: bool
    tie_break: TieBreak | None
    items: list[Standing]


class Ballot(Base):
    poll_id: UUID
    team_id: UUID
    user_id: UUID
    display_name: str
    choices: list[UUID]
    submitted_at: Ts


class BallotSubmit(Strict):
    choices: Annotated[list[UUID], Field(min_length=1, max_length=3)]

    @field_validator("choices")
    @classmethod
    def _distinct(cls, v):
        if len(set(v)) != len(v):
            raise PydanticCustomError("duplicate_items", "Pick 1 to 3 different restaurants.")
        return v


class Poll(Base):
    id: UUID
    team_id: UUID
    poll_date: str
    timezone: str
    opens_at: Ts
    closes_at: Ts
    status: PollStatus
    candidates: list[Candidate]
    winner_id: UUID | None
    winner: Restaurant | None
    no_winner: bool
    ballot_count: int
    final_scores: list[Standing] | None
    tie_break: TieBreak | None
    finalized_at: Ts | None


class PollDetail(Poll):
    standings: list[Standing]
    ballots: list[Ballot]
    my_ballot: Ballot | None
    member_count: int
    server_time: Ts


class PollPage(Base):
    items: list[Poll]
    next_cursor: str | None


class RestaurantStats(Base):
    restaurant_id: UUID
    name: str
    archived: bool
    wins_total: int
    wins_recent: int
    last_won_on: str | None
    total_points: int


class RestaurantStatsList(Base):
    recent_window: int
    closed_poll_count: int
    items: list[RestaurantStats]


class Items(Base):
    items: list[Any]
