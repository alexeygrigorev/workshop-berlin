"""Data access + domain logic (teams, restaurants, polls, ballots, lifecycle, finalization) on top of SQLAlchemy.

A ``Store`` wraps one SQLAlchemy ``Session`` (one unit of work = one request / scheduler tick / seed run). Nothing
that matters for correctness lives in process memory: all state is in the database. Domain events are queued on
the store and only published to the in-process ``EventBus`` after the transaction commits.

All time-dependent methods take ``now`` explicitly; the clock is injected at the router level.
"""
from __future__ import annotations

import secrets
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Iterator
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, lazyload
from sqlalchemy.orm.exc import StaleDataError

from . import scheduling, scoring
from .db.models import (AuthSession, Ballot, IdempotencyKey, Membership, PersonalAccessToken, Poll, Restaurant,
                        Team, User)
from .db.session import Database
from .errors import ProblemError, conflict, invalid
from .events import EventBus


def norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


class Store:
    def __init__(self, session: Session, bus: EventBus) -> None:
        self.db = session
        self.bus = bus
        self._pending_events: list[tuple] = []

    # -- transaction -----------------------------------------------------------------------
    def commit(self) -> None:
        """Commit, then publish the queued events (so subscribers never see uncommitted state)."""
        try:
            self.db.commit()
        except StaleDataError:  # concurrent update of a versioned row (If-Match style conflict)
            self.db.rollback()
            self._pending_events.clear()
            raise ProblemError(412, "precondition_failed",
                               "The resource changed since you fetched it; re-fetch and retry.")
        events, self._pending_events = self._pending_events, []
        for ev in events:
            self.bus.publish(*ev)

    def rollback(self) -> None:
        self.db.rollback()
        self._pending_events.clear()

    # -- users / auth records --------------------------------------------------------------
    def is_empty(self) -> bool:
        return self.db.scalar(select(User.id).limit(1)) is None

    def add_user(self, email: str, password_hash: str, now: datetime, display_name: str | None = None,
                 user_id: UUID | None = None) -> User:
        u = User(id=user_id or uuid.uuid4(), email=email, display_name=display_name or email.split("@")[0],
                 password_hash=password_hash, created_at=now)
        try:
            with self.db.begin_nested():  # savepoint: a lost race on the unique email only undoes this insert
                self.db.add(u)
        except IntegrityError:
            raise ProblemError(409, "email_taken", f"An account with {email} already exists. Sign in instead.")
        return u

    def user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def get_user(self, user_id: UUID) -> User | None:
        return self.db.get(User, user_id)

    def session_by_hash(self, token_hash: str) -> AuthSession | None:
        return self.db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))

    def token_by_hash(self, token_hash: str) -> PersonalAccessToken | None:
        return self.db.scalar(select(PersonalAccessToken).where(PersonalAccessToken.token_hash == token_hash))

    def get_token(self, token_id: UUID) -> PersonalAccessToken | None:
        return self.db.get(PersonalAccessToken, token_id)

    def active_tokens(self, user_id: UUID) -> list[PersonalAccessToken]:
        return list(self.db.scalars(select(PersonalAccessToken).where(
            PersonalAccessToken.user_id == user_id, PersonalAccessToken.revoked_at.is_(None))
            .order_by(PersonalAccessToken.created_at, PersonalAccessToken.id)))

    # -- teams ----------------------------------------------------------------------------
    def emit(self, team: Team, etype: str, now: datetime, poll_id: UUID | None = None, **data) -> None:
        self._pending_events.append((team.id, etype, now, poll_id,
                                     {k: (str(v) if isinstance(v, UUID) else v) for k, v in data.items()}))

    def create_team(self, owner: User, name: str, tz: str, office: str | None, open_time: str,
                    close_time: str, now: datetime, team_id: UUID | None = None) -> Team:
        t = Team(id=team_id or uuid.uuid4(), name=name, timezone=tz, office=office, open_time=open_time,
                 close_time=close_time, created_at=now, updated_at=now, version=1,
                 invite_token=secrets.token_urlsafe(18), invite_updated_at=now)
        t.members[owner.id] = Membership(user_id=owner.id, role="admin", joined_at=now)
        self.db.add(t)
        return t

    def get_team(self, team_id: UUID) -> Team | None:
        return self.db.get(Team, team_id)

    def team_by_invite(self, token: str) -> Team | None:
        t = self.db.scalar(select(Team).where(Team.invite_token == token))
        return t if t is not None and t.members else None

    def teams_of(self, user_id: UUID) -> list[Team]:
        return list(self.db.scalars(select(Team).join(Membership, Membership.team_id == Team.id)
                                    .where(Membership.user_id == user_id)))

    def is_member(self, team_id: UUID, user_id: UUID) -> bool:
        return self.db.get(Membership, (team_id, user_id)) is not None

    def validate_schedule(self, open_time: str, close_time: str) -> None:
        if open_time >= close_time:  # zero padded HH:MM compares lexicographically
            raise invalid("/close_time", "invalid_format", "open_time must be earlier than close_time.")

    def update_team_schedule(self, team: Team, now: datetime) -> None:
        """Recompute windows of polls that have not opened yet; open/closed polls keep theirs."""
        for p in self.unfinalized_polls(team):
            if now < p.opens_at:
                p.timezone = team.timezone
                p.opens_at, p.closes_at = scheduling.window(p.poll_date, team.timezone, team.open_time, team.close_time)

    # -- restaurants ----------------------------------------------------------------------
    def find_duplicate(self, team: Team, name: str, address: str | None,
                       exclude: UUID | None = None) -> Restaurant | None:
        n, a = norm(name), norm(address)
        for r in team.restaurants.values():
            if r.id == exclude or r.archived_at is not None:
                continue
            if norm(r.name) == n and (not a or not r.address or norm(r.address) == a):
                return r
        return None

    def dup_error(self, existing: Restaurant, name: str, address: str | None) -> ProblemError:
        where = f" at {address}" if address else ""
        return conflict("duplicate_restaurant", f'"{name}"{where} is already on the list.',
                        existing_restaurant_id=str(existing.id))

    def add_restaurant(self, team: Team, created_by: UUID | None, now: datetime, *, name: str,
                       cuisine=None, address=None, website_url=None, map_url=None, notes=None,
                       emit: bool = True) -> Restaurant:
        r = Restaurant(id=uuid.uuid4(), team_id=team.id, name=name, cuisine=cuisine, address=address,
                       website_url=website_url, map_url=map_url, notes=notes, archived_at=None,
                       created_by=created_by, created_at=now, updated_at=now, version=1)
        team.restaurants[r.id] = r
        if emit:
            self.emit(team, "restaurant.created", now, restaurant_id=r.id)
            self._join_open_polls(team, r, now)
        return r

    def _join_open_polls(self, team: Team, r: Restaurant, now: datetime) -> None:
        self.reconcile_team(team, now)
        for p in self.unfinalized_polls(team):
            if r.id not in p.candidate_ids:
                p.candidate_ids = [*p.candidate_ids, r.id]
                self.emit(team, "poll.updated", now, p.id)

    def set_archived(self, team: Team, r: Restaurant, archived: bool, now: datetime) -> None:
        if archived == (r.archived_at is not None):
            return
        r.archived_at = now if archived else None
        r.updated_at = now
        r.version += 1
        if archived:
            self.emit(team, "restaurant.archived", now, restaurant_id=r.id)
            self.reconcile_team(team, now)
            for p in self.unfinalized_polls(team):  # not yet opened polls drop it; open polls keep it
                if now < p.opens_at and r.id in p.candidate_ids:
                    p.candidate_ids = [c for c in p.candidate_ids if c != r.id]
                    self.emit(team, "poll.updated", now, p.id)
        else:
            self.emit(team, "restaurant.unarchived", now, restaurant_id=r.id)
            self._join_open_polls(team, r, now)

    # -- polls ----------------------------------------------------------------------------
    @staticmethod
    def status(p: Poll, now: datetime) -> str:
        if p.finalized_at is not None:
            return "closed"
        return "scheduled" if now < p.opens_at else "open"  # past closes_at is finalized by reconcile first

    def unfinalized_polls(self, team: Team) -> list[Poll]:
        return list(self.db.scalars(select(Poll).where(Poll.team_id == team.id, Poll.finalized_at.is_(None))
                                    .order_by(Poll.poll_date)))

    def closed_polls(self, team: Team) -> list[Poll]:
        """Finalized polls, newest first (ballots are not loaded)."""
        return list(self.db.scalars(select(Poll).where(Poll.team_id == team.id, Poll.finalized_at.is_not(None))
                                    .options(lazyload(Poll.ballots)).order_by(Poll.poll_date.desc())))

    def poll_for_date(self, team: Team, d: date) -> Poll | None:
        return self.db.scalar(select(Poll).where(Poll.team_id == team.id, Poll.poll_date == d))

    def poll_by_id(self, team: Team, poll_id: UUID) -> Poll | None:
        return self.db.scalar(select(Poll).where(Poll.team_id == team.id, Poll.id == poll_id))

    def query_polls(self, team: Team, now: datetime, status: str, from_: date | None, to: date | None,
                    before: date | None, limit: int) -> list[Poll]:
        """History listing; returns up to ``limit`` + 1 polls, newest first."""
        q = select(Poll).where(Poll.team_id == team.id)
        if status == "closed":
            q = q.where(Poll.finalized_at.is_not(None))
        elif status == "open":
            q = q.where(Poll.finalized_at.is_(None), Poll.opens_at <= now)
        elif status == "scheduled":
            q = q.where(Poll.finalized_at.is_(None), Poll.opens_at > now)
        if from_:
            q = q.where(Poll.poll_date >= from_)
        if to:
            q = q.where(Poll.poll_date <= to)
        if before:
            q = q.where(Poll.poll_date < before)
        return list(self.db.scalars(q.order_by(Poll.poll_date.desc()).limit(limit + 1)))

    def ensure_poll(self, team: Team, d: date, now: datetime) -> Poll:
        p = self.poll_for_date(team, d)
        if p:
            return p
        opens, closes = scheduling.window(d, team.timezone, team.open_time, team.close_time)
        cands = sorted((r for r in team.restaurants.values() if r.archived_at is None), key=lambda r: r.name.casefold())
        p = Poll(id=uuid.uuid4(), team_id=team.id, poll_date=d, timezone=team.timezone, opens_at=opens,
                 closes_at=closes, candidate_ids=[r.id for r in cands], seed=secrets.token_hex(16),
                 no_winner=False, frozen_names={}, opened_emitted=False)
        try:
            with self.db.begin_nested():  # unique (team_id, poll_date): a concurrent creator wins, we reuse its row
                self.db.add(p)
        except IntegrityError:
            existing = self.poll_for_date(team, d)
            if existing is None:
                raise
            return existing
        return p

    def current_poll(self, team: Team, now: datetime) -> Poll:
        d = scheduling.local_date(now, team.timezone)
        if scheduling.is_poll_day(d):
            existing = self.poll_for_date(team, d)
            if existing:
                return self.reconcile(team, existing, now)
            _, closes = scheduling.window(d, team.timezone, team.open_time, team.close_time)
            if team.created_at < closes:  # team existed during today's window
                return self.reconcile(team, self.ensure_poll(team, d, now), now)
        return self.reconcile(team, self.ensure_poll(team, scheduling.next_poll_day(d), now), now)

    def reconcile(self, team: Team, p: Poll, now: datetime) -> Poll:
        """Bring a poll to its canonical state for ``now`` (idempotent): finalize if past closes_at, emit opened."""
        if p.finalized_at is None and now >= p.closes_at:
            self.finalize(team, p, now)
        if p.finalized_at is None and now >= p.opens_at and not p.opened_emitted:
            p.opened_emitted = True
            self.emit(team, "poll.opened", now, p.id)
        return p

    def reconcile_team(self, team: Team, now: datetime) -> None:
        for p in self.unfinalized_polls(team):
            self.reconcile(team, p, now)

    def tick(self, now: datetime) -> None:
        """Scheduler pass: create today's/next poll, open and finalize on time. Safe to run any number of times."""
        for team in list(self.db.scalars(select(Team))):
            if not team.members:
                continue
            self.current_poll(team, now)
            d = scheduling.local_date(now, team.timezone)
            self.ensure_poll(team, scheduling.next_poll_day(d), now)
            self.reconcile_team(team, now)

    def lock_poll(self, p: Poll) -> Poll:
        """Re-read the poll row inside the transaction with ``SELECT ... FOR UPDATE`` (a no-op on SQLite).

        Serialises ballot writes against finalization (and finalizations against each other) on backends with
        row locks; callers must re-check state (finalized_at, candidates) afterwards.
        """
        self.db.flush()
        self.db.refresh(p, with_for_update=True)
        return p

    def finalize(self, team: Team, p: Poll, now: datetime) -> Poll:
        if p.finalized_at is not None:
            return p
        self.lock_poll(p)
        if p.finalized_at is not None:  # finalized concurrently while we waited for the lock
            return p
        names = {cid: team.restaurants[cid].name for cid in p.candidate_ids if cid in team.restaurants}
        tallies = scoring.tally(names, [b.choices for b in p.ballots.values()])
        res = scoring.finalize(tallies, len(p.ballots), p.seed)
        p.frozen_names = names
        p.final_scores = [self._standing(t, i + 1) for i, t in enumerate(res.ordered)]
        p.winner_id, p.no_winner, p.tie_break = res.winner_id, res.no_winner, res.tie_break
        for b in p.ballots.values():
            u = self.get_user(b.user_id)
            b.display_name = u.display_name if u else "Former member"
        p.finalized_at = now
        p.opened_emitted = True
        self.emit(team, "poll.closed", now, p.id, winner_id=str(p.winner_id) if p.winner_id else None,
                  no_winner=p.no_winner, tie_break=p.tie_break)
        return p

    @staticmethod
    def _standing(t: scoring.Tally, position: int) -> dict:
        return {"restaurant_id": t.restaurant_id, "name": t.name, "score": t.score, "first_count": t.first,
                "second_count": t.second, "third_count": t.third, "position": position}

    def standings(self, team: Team, p: Poll) -> list[dict]:
        if p.finalized_at is not None and p.final_scores is not None:
            return p.final_scores
        names = {cid: team.restaurants[cid].name for cid in p.candidate_ids if cid in team.restaurants}
        tallies = scoring.tally(names, [b.choices for b in p.ballots.values()])
        return [self._standing(t, i + 1) for i, t in enumerate(scoring.display_order(tallies))]

    def leader_ids(self, standings: list[dict], p: Poll) -> list[UUID]:
        if p.finalized_at is not None or not p.ballots or not standings:
            return []
        top = standings[0]["score"]
        return [s["restaurant_id"] for s in standings if s["score"] == top and top > 0]

    def sorted_ballots(self, p: Poll) -> list[Ballot]:
        return sorted(p.ballots.values(), key=lambda b: (b.submitted_at, str(b.user_id)))

    def ballot_name(self, b: Ballot) -> str:
        if b.display_name:
            return b.display_name
        u = self.get_user(b.user_id)
        return u.display_name if u else "Former member"

    def upsert_ballot(self, p: Poll, user_id: UUID, choices: list[UUID], now: datetime) -> tuple[Ballot, bool]:
        """Create or replace the member's ballot (one row per (poll, user)); returns (ballot, replaced).

        The caller holds the poll lock (``lock_poll``) so the replace is atomic with the accepting-window check.
        """
        b = p.ballots.get(user_id)
        if b is not None:
            b.choices, b.submitted_at = list(choices), now
            return b, True
        b = Ballot(user_id=user_id, choices=list(choices), submitted_at=now)
        p.ballots[user_id] = b
        return b, False

    # -- idempotency ----------------------------------------------------------------------
    def idem_get(self, user_id: UUID, key: str, now: datetime):
        self.db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < now - timedelta(hours=24)))
        row = self.db.get(IdempotencyKey, (user_id, key))
        return (row.fingerprint, row.status, row.body, row.headers, row.created_at) if row else None

    def idem_put(self, user_id: UUID, key: str, fingerprint: str, status: int, body: dict, headers: dict,
                 now: datetime) -> None:
        self.db.merge(IdempotencyKey(user_id=user_id, key=key, fingerprint=fingerprint, status=status, body=body,
                                     headers=headers, created_at=now))


@contextmanager
def unit_of_work(db: Database, bus: EventBus) -> Iterator[Store]:
    """One transaction: commit (then publish events) on success, roll back on any exception."""
    session = db.session_factory()
    store = Store(session, bus)
    try:
        yield store
        store.commit()
    except BaseException:
        store.rollback()
        raise
    finally:
        session.close()
