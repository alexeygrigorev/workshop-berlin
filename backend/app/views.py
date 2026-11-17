"""Builders that turn store records into API models."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi.responses import JSONResponse

from . import models as m
from .errors import ProblemError
from .scheduling import WEEKDAYS
from .db.models import Ballot, Poll, Restaurant, Team, User
from .store import Store


def user_view(u: User) -> m.User:
    return m.User(id=u.id, email=u.email, display_name=u.display_name, created_at=u.created_at)


def team_ref(t: Team) -> m.TeamRef:
    return m.TeamRef(id=t.id, name=t.name, timezone=t.timezone)


def team_view(t: Team, role: str) -> m.Team:
    return m.Team(id=t.id, name=t.name, timezone=t.timezone, office=t.office,
                  schedule=m.Schedule(open_time=t.open_time, close_time=t.close_time, weekdays=WEEKDAYS),
                  my_role=role, member_count=len(t.members), created_at=t.created_at, updated_at=t.updated_at)


def team_etag(t: Team) -> str:
    return f'"t-{t.version}"'


def restaurant_view(r: Restaurant) -> m.Restaurant:
    return m.Restaurant(**{f: getattr(r, f) for f in (
        "id", "team_id", "name", "cuisine", "address", "website_url", "map_url", "notes", "archived_at",
        "created_by", "created_at", "updated_at")})


def restaurant_etag(r: Restaurant) -> str:
    return f'"r-{r.version}"'


def ballot_view(store: Store, p: Poll, b: Ballot) -> m.Ballot:
    return m.Ballot(poll_id=p.id, team_id=p.team_id, user_id=b.user_id, display_name=store.ballot_name(b),
                    choices=b.choices, submitted_at=b.submitted_at)


def poll_view(store: Store, team: Team, p: Poll, now: datetime) -> m.Poll:
    closed = p.finalized_at is not None
    names = p.frozen_names if closed else {}
    cands = []
    for cid in p.candidate_ids:
        r = team.restaurants.get(cid)
        if r is None:
            continue
        cands.append(m.Candidate(id=cid, name=names.get(cid, r.name) if closed else r.name,
                                 archived=r.archived_at is not None))
    cands.sort(key=lambda c: (c.name.casefold(), str(c.id)))
    winner = team.restaurants.get(p.winner_id) if p.winner_id else None
    return m.Poll(
        id=p.id, team_id=p.team_id, poll_date=p.poll_date.isoformat(), timezone=p.timezone, opens_at=p.opens_at,
        closes_at=p.closes_at, status=store.status(p, now), candidates=cands, winner_id=p.winner_id,
        winner=restaurant_view(winner) if winner else None, no_winner=p.no_winner, ballot_count=len(p.ballots),
        final_scores=[m.Standing(**s) for s in p.final_scores] if p.final_scores is not None else None,
        tie_break=p.tie_break, finalized_at=p.finalized_at)


def poll_detail(store: Store, team: Team, p: Poll, now: datetime, user_id: UUID) -> m.PollDetail:
    base = poll_view(store, team, p, now)
    ballots = [ballot_view(store, p, b) for b in store.sorted_ballots(p)]
    mine = p.ballots.get(user_id)
    return m.PollDetail(**base.model_dump(), standings=[m.Standing(**s) for s in store.standings(team, p)],
                        ballots=ballots, my_ballot=ballot_view(store, p, mine) if mine else None,
                        member_count=len(team.members), server_time=now)


def respond(model, status: int = 200, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(model.model_dump(mode="json"), status_code=status, headers=headers)


def idem_replay(store: Store, user_id: UUID, key: str | None, fingerprint: str, now: datetime) -> JSONResponse | None:
    if not key:
        return None
    hit = store.idem_get(user_id, key, now)
    if not hit:
        return None
    fp, status, body, headers, _ = hit
    if fp != fingerprint:
        raise ProblemError(409, "idempotency_key_reused", "This Idempotency-Key was already used with a different request.")
    return JSONResponse(body, status_code=status, headers=headers)


def created(store: Store, user_id: UUID, key: str | None, fingerprint: str, now: datetime, model,
            headers: dict | None = None) -> JSONResponse:
    body = model.model_dump(mode="json")
    if key:
        store.idem_put(user_id, key, fingerprint, 201, body, headers or {}, now)
    return JSONResponse(body, status_code=201, headers=headers)
