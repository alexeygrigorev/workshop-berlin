"""Polls: history list, current poll, by date, detail, standings, finalize."""
from __future__ import annotations

import base64
import json
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from .. import models as m
from ..deps import TeamCtx, get_poll, team_access
from ..errors import ProblemError, invalid, not_found
from ..views import poll_detail, poll_view

router = APIRouter(prefix="/v1/teams/{teamId}", tags=["Polls"])


def _encode_cursor(d: date) -> str:
    return base64.urlsafe_b64encode(json.dumps({"d": d.isoformat()}, separators=(",", ":")).encode()).decode().rstrip("=")


def _decode_cursor(c: str) -> date:
    try:
        raw = base64.urlsafe_b64decode(c + "=" * (-len(c) % 4))
        return date.fromisoformat(json.loads(raw)["d"])
    except Exception:
        raise invalid("?cursor", "invalid_format", "Invalid cursor.")


@router.get("/polls", operation_id="listPolls", response_model=m.PollPage)
async def list_polls(status: Literal["closed", "open", "scheduled", "any"] = "closed",
                     from_: date | None = Query(default=None, alias="from"),
                     to: date | None = None,
                     limit: int = Query(default=20, ge=1, le=100),
                     cursor: str | None = None,
                     ctx: TeamCtx = Depends(team_access("read"))):
    st, team = ctx.store, ctx.team
    st.reconcile_team(team, ctx.now)
    before = _decode_cursor(cursor) if cursor else None
    polls = st.query_polls(team, ctx.now, status, from_, to, before, limit)  # limit + 1 rows
    page = polls[:limit]
    next_cursor = _encode_cursor(page[-1].poll_date) if len(polls) > limit else None
    return m.PollPage(items=[poll_view(st, team, p, ctx.now) for p in page], next_cursor=next_cursor)


@router.get("/polls/current", operation_id="getCurrentPoll", response_model=m.PollDetail)
async def get_current_poll(ctx: TeamCtx = Depends(team_access("read"))):
    p = ctx.store.current_poll(ctx.team, ctx.now)
    return poll_detail(ctx.store, ctx.team, p, ctx.now, ctx.principal.user.id)


@router.get("/polls-by-date/{pollDate}", operation_id="getPollByDate", response_model=m.PollDetail)
async def get_poll_by_date(poll_date: date = Path(alias="pollDate"), ctx: TeamCtx = Depends(team_access("read"))):
    p = ctx.store.poll_for_date(ctx.team, poll_date)
    if not p:
        raise not_found(f"No poll exists for {poll_date.isoformat()}.")
    ctx.store.reconcile(ctx.team, p, ctx.now)
    return poll_detail(ctx.store, ctx.team, p, ctx.now, ctx.principal.user.id)


@router.get("/polls/{pollId}", operation_id="getPoll", response_model=m.PollDetail)
async def get_poll_detail(poll_id: UUID = Path(alias="pollId"), ctx: TeamCtx = Depends(team_access("read"))):
    p = get_poll(ctx, poll_id)
    return poll_detail(ctx.store, ctx.team, p, ctx.now, ctx.principal.user.id)


@router.get("/polls/{pollId}/standings", operation_id="getPollStandings", response_model=m.Standings)
async def get_standings(poll_id: UUID = Path(alias="pollId"), ctx: TeamCtx = Depends(team_access("read"))):
    p = get_poll(ctx, poll_id)
    st = ctx.store
    items = st.standings(ctx.team, p)
    return m.Standings(poll_id=p.id, status=st.status(p, ctx.now), final=p.finalized_at is not None,
                       ballot_count=len(p.ballots), member_count=len(ctx.team.members),
                       leader_ids=st.leader_ids(items, p), winner_id=p.winner_id, no_winner=p.no_winner,
                       tie_break=p.tie_break, items=[m.Standing(**s) for s in items])


@router.post("/polls/{pollId}/finalize", operation_id="finalizePoll", response_model=m.Poll)
async def finalize_poll(poll_id: UUID = Path(alias="pollId"), ctx: TeamCtx = Depends(team_access("write"))):
    p = ctx.store.poll_by_id(ctx.team, poll_id)
    if not p:
        raise not_found(f"Poll {poll_id} does not exist in this team.")
    if p.finalized_at is None and ctx.now < p.closes_at:
        raise ProblemError(409, "poll_not_closable",
                           f"This poll closes at {m.fmt_ts(p.closes_at)}.")
    ctx.store.reconcile(ctx.team, p, ctx.now)  # idempotent; never closes early
    return poll_view(ctx.store, ctx.team, p, ctx.now)
