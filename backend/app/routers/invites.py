"""Invites: getInviteInfo, joinTeam, getTeamInvite, revokeTeamInvite, regenerateTeamInvite."""
from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Path, Request, Response

from .. import models as m
from ..auth import Principal, get_now, get_store, require
from ..deps import TeamCtx, team_access
from ..errors import ProblemError
from ..store import Membership, Store, TeamRec
from ..views import team_ref

public_router = APIRouter(prefix="/v1/invites", tags=["Invites"])
team_router = APIRouter(prefix="/v1/teams/{teamId}/invite", tags=["Invites"])


def _invalid() -> ProblemError:
    return ProblemError(404, "invite_invalid",
                        "This invite link is invalid or was revoked. Ask your team admin for a new one.")


def _invite_view(request: Request, t: TeamRec) -> m.Invite:
    active = t.invite_token is not None
    url = f"{request.app.state.settings.invite_origin}/join/{t.invite_token}" if active else None
    return m.Invite(active=active, token=t.invite_token, url=url, updated_at=t.invite_updated_at or t.created_at)


@public_router.get("/{inviteToken}", operation_id="getInviteInfo", response_model=m.InvitePreview)
async def get_invite_info(invite_token: str = Path(alias="inviteToken", min_length=16, max_length=128),
                          p: Principal = Depends(require("read")), store: Store = Depends(get_store)):
    t = store.team_by_invite(invite_token)
    if not t:
        raise _invalid()
    return m.InvitePreview(team_id=t.id, team_name=t.name, member_count=len(t.members),
                           already_member=p.user.id in t.members)


@public_router.post("/{inviteToken}/accept", operation_id="joinTeam", response_model=m.JoinResult)
async def join_team(response: Response, invite_token: str = Path(alias="inviteToken", min_length=16, max_length=128),
                    p: Principal = Depends(require("write")), store: Store = Depends(get_store),
                    now: datetime = Depends(get_now)):
    t = store.team_by_invite(invite_token)
    if not t:
        raise _invalid()
    existing = t.members.get(p.user.id)
    if existing:
        return m.JoinResult(joined=False, role=existing.role, team=team_ref(t))
    t.members[p.user.id] = Membership(p.user.id, "member", now)
    store.emit(t, "member.joined", now, user_id=p.user.id, role="member")
    response.status_code = 201
    return m.JoinResult(joined=True, role="member", team=team_ref(t))


@team_router.get("", operation_id="getTeamInvite", response_model=m.Invite)
async def get_team_invite(request: Request, ctx: TeamCtx = Depends(team_access("read"))):
    return _invite_view(request, ctx.team)


@team_router.delete("", operation_id="revokeTeamInvite", response_model=m.Invite)
async def revoke_team_invite(request: Request, ctx: TeamCtx = Depends(team_access("write", admin=True))):
    t = ctx.team
    if t.invite_token is not None:
        t.invite_token, t.invite_updated_at = None, ctx.now
        ctx.store.emit(t, "invite.changed", ctx.now)
    return _invite_view(request, t)


@team_router.post("/regenerate", operation_id="regenerateTeamInvite", response_model=m.Invite)
async def regenerate_team_invite(request: Request, ctx: TeamCtx = Depends(team_access("write", admin=True))):
    t = ctx.team
    t.invite_token, t.invite_updated_at = secrets.token_urlsafe(18), ctx.now
    ctx.store.emit(t, "invite.changed", ctx.now)
    return _invite_view(request, t)
