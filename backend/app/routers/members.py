"""Members: listMembers, leaveTeam, updateMemberRole, removeMember."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response

from .. import models as m
from ..deps import TeamCtx, team_access
from ..errors import conflict, not_found

router = APIRouter(prefix="/v1/teams/{teamId}/members", tags=["Members"])


def _member_view(ctx: TeamCtx, user_id: UUID) -> m.Member:
    mem = ctx.team.members[user_id]
    u = ctx.store.users[user_id]
    return m.Member(user_id=user_id, display_name=u.display_name, role=mem.role, joined_at=mem.joined_at)


@router.get("", operation_id="listMembers", response_model=m.Items)
async def list_members(ctx: TeamCtx = Depends(team_access("read"))):
    ms = sorted(ctx.team.members.values(), key=lambda x: (x.joined_at, str(x.user_id)))
    return {"items": [_member_view(ctx, x.user_id).model_dump(mode="json") for x in ms]}


@router.delete("/me", operation_id="leaveTeam", status_code=204)
async def leave_team(ctx: TeamCtx = Depends(team_access("write"))):
    t, uid = ctx.team, ctx.principal.user.id
    if ctx.me.role == "admin" and t.admin_count() == 1 and len(t.members) > 1:
        raise conflict("last_admin", "Promote another member to admin first.")
    del t.members[uid]
    ctx.store.emit(t, "member.left", ctx.now, user_id=uid)
    return Response(status_code=204)


@router.patch("/{userId}", operation_id="updateMemberRole", response_model=m.Member)
async def update_member_role(body: m.MemberUpdate, user_id: UUID = Path(alias="userId"),
                             ctx: TeamCtx = Depends(team_access("write", admin=True))):
    t = ctx.team
    target = t.members.get(user_id)
    if not target:
        raise not_found("That user is not a member of this team.")
    if target.role != body.role:
        if target.role == "admin" and t.admin_count() == 1:
            raise conflict("last_admin", "Promote another member to admin first.")
        target.role = body.role
        ctx.store.emit(t, "member.role_changed", ctx.now, user_id=user_id, role=body.role)
    return _member_view(ctx, user_id)


@router.delete("/{userId}", operation_id="removeMember", status_code=204)
async def remove_member(user_id: UUID = Path(alias="userId"), ctx: TeamCtx = Depends(team_access("write", admin=True))):
    t = ctx.team
    target = t.members.get(user_id)
    if not target:
        raise not_found("That user is not a member of this team.")
    if target.role == "admin" and t.admin_count() == 1:
        raise conflict("last_admin", "Promote another member to admin first.")
    del t.members[user_id]
    ctx.store.emit(t, "member.removed", ctx.now, user_id=user_id)
    return Response(status_code=204)
