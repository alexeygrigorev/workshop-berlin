"""In-memory store and domain logic (teams, restaurants, polls, ballots, lifecycle, finalization).

Everything runs on the single asyncio event loop (all routes are ``async def``), so no locking is needed.
All time-dependent methods take ``now`` explicitly; the clock is injected at the router level.
"""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from uuid import UUID

from . import scheduling, scoring
from .errors import ProblemError, conflict, invalid
from .events import EventBus


def norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


@dataclass
class UserRec:
    id: UUID
    email: str
    display_name: str
    password_hash: str
    created_at: datetime


@dataclass
class SessionRec:
    id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked: bool = False


@dataclass
class TokenRec:
    id: UUID
    user_id: UUID
    name: str
    scopes: list[str]
    token_hash: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass
class Membership:
    user_id: UUID
    role: str
    joined_at: datetime


@dataclass
class RestaurantRec:
    id: UUID
    team_id: UUID
    name: str
    cuisine: str | None
    address: str | None
    website_url: str | None
    map_url: str | None
    notes: str | None
    archived_at: datetime | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    version: int = 1


@dataclass
class BallotRec:
    user_id: UUID
    choices: list[UUID]
    submitted_at: datetime
    display_name: str | None = None  # frozen at finalization


@dataclass
class PollRec:
    id: UUID
    team_id: UUID
    poll_date: date
    timezone: str
    opens_at: datetime
    closes_at: datetime
    candidate_ids: list[UUID]
    seed: str  # private; never exposed
    ballots: dict[UUID, BallotRec] = field(default_factory=dict)
    finalized_at: datetime | None = None
    winner_id: UUID | None = None
    no_winner: bool = False
    tie_break: str | None = None
    final_scores: list[dict] | None = None
    frozen_names: dict[UUID, str] = field(default_factory=dict)
    opened_emitted: bool = False


@dataclass
class TeamRec:
    id: UUID
    name: str
    timezone: str
    office: str | None
    open_time: str
    close_time: str
    created_at: datetime
    updated_at: datetime
    members: dict[UUID, Membership] = field(default_factory=dict)
    restaurants: dict[UUID, RestaurantRec] = field(default_factory=dict)
    polls: dict[UUID, PollRec] = field(default_factory=dict)
    invite_token: str | None = None
    invite_updated_at: datetime | None = None
    version: int = 1

    def admin_count(self) -> int:
        return sum(1 for m in self.members.values() if m.role == "admin")


class Store:
    def __init__(self, bus: EventBus | None = None) -> None:
        self.bus = bus or EventBus()
        self.users: dict[UUID, UserRec] = {}
        self.users_by_email: dict[str, UUID] = {}
        self.sessions: dict[UUID, SessionRec] = {}
        self.sessions_by_hash: dict[str, UUID] = {}
        self.tokens: dict[UUID, TokenRec] = {}
        self.tokens_by_hash: dict[str, UUID] = {}
        self.teams: dict[UUID, TeamRec] = {}
        self.idempotency: dict[tuple, tuple] = {}

    # -- users / auth records --------------------------------------------------------------
    def add_user(self, email: str, password_hash: str, now: datetime, display_name: str | None = None,
                 user_id: UUID | None = None) -> UserRec:
        u = UserRec(user_id or uuid.uuid4(), email, display_name or email.split("@")[0], password_hash, now)
        self.users[u.id] = u
        self.users_by_email[email] = u.id
        return u

    def user_by_email(self, email: str) -> UserRec | None:
        uid = self.users_by_email.get(email)
        return self.users[uid] if uid else None

    # -- teams ----------------------------------------------------------------------------
    def emit(self, team: TeamRec, etype: str, now: datetime, poll_id: UUID | None = None, **data) -> None:
        self.bus.publish(team.id, etype, now, poll_id, {k: (str(v) if isinstance(v, UUID) else v) for k, v in data.items()})

    def create_team(self, owner: UserRec, name: str, tz: str, office: str | None, open_time: str,
                    close_time: str, now: datetime, team_id: UUID | None = None) -> TeamRec:
        t = TeamRec(team_id or uuid.uuid4(), name, tz, office, open_time, close_time, now, now)
        t.members[owner.id] = Membership(owner.id, "admin", now)
        t.invite_token = secrets.token_urlsafe(18)
        t.invite_updated_at = now
        self.teams[t.id] = t
        return t

    def team_by_invite(self, token: str) -> TeamRec | None:
        for t in self.teams.values():
            if t.invite_token and secrets.compare_digest(t.invite_token, token) and t.members:
                return t
        return None

    def teams_of(self, user_id: UUID) -> list[TeamRec]:
        return [t for t in self.teams.values() if user_id in t.members]

    def validate_schedule(self, open_time: str, close_time: str) -> None:
        if open_time >= close_time:  # zero padded HH:MM compares lexicographically
            raise invalid("/close_time", "invalid_format", "open_time must be earlier than close_time.")

    def update_team_schedule(self, team: TeamRec, now: datetime) -> None:
        """Recompute windows of polls that have not opened yet; open/closed polls keep theirs."""
        for p in team.polls.values():
            if p.finalized_at is None and now < p.opens_at:
                p.timezone = team.timezone
                p.opens_at, p.closes_at = scheduling.window(p.poll_date, team.timezone, team.open_time, team.close_time)

    # -- restaurants ----------------------------------------------------------------------
    def find_duplicate(self, team: TeamRec, name: str, address: str | None,
                       exclude: UUID | None = None) -> RestaurantRec | None:
        n, a = norm(name), norm(address)
        for r in team.restaurants.values():
            if r.id == exclude or r.archived_at is not None:
                continue
            if norm(r.name) == n and (not a or not r.address or norm(r.address) == a):
                return r
        return None

    def dup_error(self, existing: RestaurantRec, name: str, address: str | None) -> ProblemError:
        where = f" at {address}" if address else ""
        return conflict("duplicate_restaurant", f'"{name}"{where} is already on the list.',
                        existing_restaurant_id=str(existing.id))

    def add_restaurant(self, team: TeamRec, created_by: UUID | None, now: datetime, *, name: str,
                       cuisine=None, address=None, website_url=None, map_url=None, notes=None,
                       emit: bool = True) -> RestaurantRec:
        r = RestaurantRec(uuid.uuid4(), team.id, name, cuisine, address, website_url, map_url, notes, None,
                          created_by, now, now)
        team.restaurants[r.id] = r
        if emit:
            self.emit(team, "restaurant.created", now, restaurant_id=r.id)
            self._join_open_polls(team, r, now)
        return r

    def _join_open_polls(self, team: TeamRec, r: RestaurantRec, now: datetime) -> None:
        self.reconcile_team(team, now)
        for p in team.polls.values():
            if p.finalized_at is None and r.id not in p.candidate_ids:
                p.candidate_ids.append(r.id)
                self.emit(team, "poll.updated", now, p.id)

    def set_archived(self, team: TeamRec, r: RestaurantRec, archived: bool, now: datetime) -> None:
        if archived == (r.archived_at is not None):
            return
        r.archived_at = now if archived else None
        r.updated_at = now
        r.version += 1
        if archived:
            self.emit(team, "restaurant.archived", now, restaurant_id=r.id)
            self.reconcile_team(team, now)
            for p in team.polls.values():  # not yet opened polls drop it; open polls keep it (existing ballots stay valid)
                if p.finalized_at is None and now < p.opens_at and r.id in p.candidate_ids:
                    p.candidate_ids.remove(r.id)
                    self.emit(team, "poll.updated", now, p.id)
        else:
            self.emit(team, "restaurant.unarchived", now, restaurant_id=r.id)
            self._join_open_polls(team, r, now)

    # -- polls ----------------------------------------------------------------------------
    @staticmethod
    def status(p: PollRec, now: datetime) -> str:
        if p.finalized_at is not None:
            return "closed"
        return "scheduled" if now < p.opens_at else "open"  # past closes_at is finalized by reconcile first

    def poll_for_date(self, team: TeamRec, d: date) -> PollRec | None:
        for p in team.polls.values():
            if p.poll_date == d:
                return p
        return None

    def ensure_poll(self, team: TeamRec, d: date, now: datetime) -> PollRec:
        p = self.poll_for_date(team, d)
        if p:
            return p
        opens, closes = scheduling.window(d, team.timezone, team.open_time, team.close_time)
        cands = sorted((r for r in team.restaurants.values() if r.archived_at is None), key=lambda r: r.name.casefold())
        p = PollRec(uuid.uuid4(), team.id, d, team.timezone, opens, closes, [r.id for r in cands], secrets.token_hex(16))
        team.polls[p.id] = p
        return p

    def current_poll(self, team: TeamRec, now: datetime) -> PollRec:
        d = scheduling.local_date(now, team.timezone)
        if scheduling.is_poll_day(d):
            existing = self.poll_for_date(team, d)
            if existing:
                return self.reconcile(team, existing, now)
            _, closes = scheduling.window(d, team.timezone, team.open_time, team.close_time)
            if team.created_at < closes:  # team existed during today's window
                return self.reconcile(team, self.ensure_poll(team, d, now), now)
        return self.reconcile(team, self.ensure_poll(team, scheduling.next_poll_day(d), now), now)

    def reconcile(self, team: TeamRec, p: PollRec, now: datetime) -> PollRec:
        """Bring a poll to its canonical state for ``now`` (idempotent): finalize if past closes_at, emit opened."""
        if p.finalized_at is None and now >= p.closes_at:
            self.finalize(team, p, now)
        if p.finalized_at is None and now >= p.opens_at and not p.opened_emitted:
            p.opened_emitted = True
            self.emit(team, "poll.opened", now, p.id)
        return p

    def reconcile_team(self, team: TeamRec, now: datetime) -> None:
        for p in list(team.polls.values()):
            self.reconcile(team, p, now)

    def tick(self, now: datetime) -> None:
        """Scheduler pass: create today's/next poll, open and finalize on time. Safe to run any number of times."""
        for team in list(self.teams.values()):
            if not team.members:
                continue
            self.current_poll(team, now)
            d = scheduling.local_date(now, team.timezone)
            self.ensure_poll(team, scheduling.next_poll_day(d), now)
            self.reconcile_team(team, now)

    def finalize(self, team: TeamRec, p: PollRec, now: datetime) -> PollRec:
        if p.finalized_at is not None:
            return p
        names = {cid: team.restaurants[cid].name for cid in p.candidate_ids if cid in team.restaurants}
        tallies = scoring.tally(names, [b.choices for b in p.ballots.values()])
        res = scoring.finalize(tallies, len(p.ballots), p.seed)
        p.frozen_names = names
        p.final_scores = [self._standing(t, i + 1) for i, t in enumerate(res.ordered)]
        p.winner_id, p.no_winner, p.tie_break = res.winner_id, res.no_winner, res.tie_break
        for b in p.ballots.values():
            u = self.users.get(b.user_id)
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

    def standings(self, team: TeamRec, p: PollRec) -> list[dict]:
        if p.finalized_at is not None and p.final_scores is not None:
            return p.final_scores
        names = {cid: team.restaurants[cid].name for cid in p.candidate_ids if cid in team.restaurants}
        tallies = scoring.tally(names, [b.choices for b in p.ballots.values()])
        return [self._standing(t, i + 1) for i, t in enumerate(scoring.display_order(tallies))]

    def leader_ids(self, standings: list[dict], p: PollRec) -> list[UUID]:
        if p.finalized_at is not None or not p.ballots or not standings:
            return []
        top = standings[0]["score"]
        return [s["restaurant_id"] for s in standings if s["score"] == top and top > 0]

    def sorted_ballots(self, p: PollRec) -> list[BallotRec]:
        return sorted(p.ballots.values(), key=lambda b: (b.submitted_at, str(b.user_id)))

    def ballot_name(self, b: BallotRec) -> str:
        if b.display_name:
            return b.display_name
        u = self.users.get(b.user_id)
        return u.display_name if u else "Former member"

    # -- idempotency ----------------------------------------------------------------------
    def idem_get(self, user_id: UUID, key: str, now: datetime):
        for k in [k for k, v in self.idempotency.items() if now - v[4] > timedelta(hours=24)]:
            del self.idempotency[k]
        return self.idempotency.get((user_id, key))

    def idem_put(self, user_id: UUID, key: str, fingerprint: str, status: int, body: dict, headers: dict,
                 now: datetime) -> None:
        self.idempotency[(user_id, key)] = (fingerprint, status, body, headers, now)
