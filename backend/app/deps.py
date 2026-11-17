"""Shared FastAPI dependencies: team membership / admin checks, idempotency, ETags."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from uuid import UUID

from fastapi import Depends, Header, Path

from .auth import Principal, get_now, get_store, require
from .errors import ProblemError, forbidden, not_found
from .store import Membership, PollRec, Store, TeamRec


@dataclass
class TeamCtx:
    team: TeamRec
    me: Membership
    principal: Principal
    store: Store
    now: datetime


def team_access(scope: str, admin: bool = False) -> Callable:
    async def dep(team_id: UUID = Path(alias="teamId"), principal: Principal = Depends(require(scope)),
                  store: Store = Depends(get_store), now: datetime = Depends(get_now)) -> TeamCtx:
        team = store.teams.get(team_id)
        me = team.members.get(principal.user.id) if team else None
        if not team or not me:
            raise forbidden("not_a_member", "You are not a member of this team.")
        if admin and me.role != "admin":
            raise forbidden("admins_only", "Only team admins can do this.")
        return TeamCtx(team, me, principal, store, now)
    return dep


def get_poll(ctx: TeamCtx, poll_id: UUID) -> PollRec:
    p = ctx.team.polls.get(poll_id)
    if not p:
        raise not_found(f"Poll {poll_id} does not exist in this team.")
    return ctx.store.reconcile(ctx.team, p, ctx.now)


def check_if_match(if_match: str | None, etag: str) -> None:
    if if_match is None or if_match.strip() == "*":
        return
    candidates = {c.strip().removeprefix("W/") for c in if_match.split(",")}
    if etag not in candidates:
        raise ProblemError(412, "precondition_failed", "The resource changed since you fetched it; re-fetch and retry.")


def if_match_header(if_match: str | None = Header(default=None, alias="If-Match")) -> str | None:
    return if_match


def idempotency_header(key: str | None = Header(default=None, alias="Idempotency-Key", max_length=255)) -> str | None:
    return key
