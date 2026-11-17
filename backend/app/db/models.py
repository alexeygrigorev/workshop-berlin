"""SQLAlchemy 2.0 ORM models (persistence). API schemas live in ``app/models.py``.

Only portable types/constructs are used so the same schema runs on SQLite and PostgreSQL. Collections that the
domain code treats as dicts (members, restaurants, ballots) are mapped as keyed collections.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (JSON, Boolean, Date, ForeignKey, Integer, MetaData, String, Text, UniqueConstraint, Uuid)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.orm.collections import attribute_keyed_dict

from .types import Standings, UtcDateTime, UuidKeyedNames, UuidList


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored lower-cased by the API layer
    display_name: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class AuthSession(Base):
    """Bearer / cookie session. Only the SHA-256 of the token is stored."""
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class PersonalAccessToken(Base):
    """Personal API token with scopes. Only the SHA-256 of the token is stored (plus a display prefix)."""
    __tablename__ = "api_tokens"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    scopes: Mapped[list[str]] = mapped_column(JSON)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class Membership(Base):
    __tablename__ = "memberships"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(16))
    joined_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Team(Base):
    __tablename__ = "teams"
    # optimistic concurrency: UPDATEs are guarded by ``WHERE version = <old>`` (the API bumps it explicitly)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64))
    office: Mapped[str | None] = mapped_column(String(200), nullable=True)
    open_time: Mapped[str] = mapped_column(String(5))
    close_time: Mapped[str] = mapped_column(String(5))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
    invite_token: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    invite_updated_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    members: Mapped[dict[UUID, Membership]] = relationship(
        collection_class=attribute_keyed_dict("user_id"), cascade="all, delete-orphan", lazy="selectin")
    restaurants: Mapped[dict[UUID, Restaurant]] = relationship(
        collection_class=attribute_keyed_dict("id"), cascade="all, delete-orphan", lazy="selectin")

    def admin_count(self) -> int:
        return sum(1 for m in self.members.values() if m.role == "admin")


class Restaurant(Base):
    __tablename__ = "restaurants"
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    cuisine: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    map_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Poll(Base):
    __tablename__ = "polls"
    __table_args__ = (UniqueConstraint("team_id", "poll_date"),)  # one poll per team per local day

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    poll_date: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64))
    opens_at: Mapped[datetime] = mapped_column(UtcDateTime)
    closes_at: Mapped[datetime] = mapped_column(UtcDateTime)
    candidate_ids: Mapped[list[UUID]] = mapped_column(UuidList)
    seed: Mapped[str] = mapped_column(String(64))  # private tie-break seed; never exposed
    finalized_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    winner_id: Mapped[UUID | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True)
    no_winner: Mapped[bool] = mapped_column(Boolean, default=False)
    tie_break: Mapped[str | None] = mapped_column(String(32), nullable=True)
    final_scores: Mapped[list[dict] | None] = mapped_column(Standings, nullable=True)
    frozen_names: Mapped[dict[UUID, str]] = mapped_column(UuidKeyedNames, default=dict)
    opened_emitted: Mapped[bool] = mapped_column(Boolean, default=False)

    ballots: Mapped[dict[UUID, Ballot]] = relationship(
        collection_class=attribute_keyed_dict("user_id"), cascade="all, delete-orphan", lazy="selectin")


class Ballot(Base):
    __tablename__ = "ballots"

    # (poll_id, user_id) is the primary key: one ballot per member per poll
    poll_id: Mapped[UUID] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    choices: Mapped[list[UUID]] = mapped_column(UuidList)
    submitted_at: Mapped[datetime] = mapped_column(UtcDateTime)
    display_name: Mapped[str | None] = mapped_column(String(254), nullable=True)  # frozen at finalization


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(Text)
    status: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict] = mapped_column(JSON)
    headers: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
