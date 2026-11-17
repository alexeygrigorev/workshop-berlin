"""Teams: createTeam, getTeam, updateTeam."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response

from .. import models as m
from ..auth import Principal, get_now, get_store, require
from ..deps import TeamCtx, check_if_match, idempotency_header, if_match_header, team_access
from ..store import Store
from ..views import created, idem_replay, team_etag, team_view

router = APIRouter(prefix="/v1/teams", tags=["Teams"])


@router.post("", operation_id="createTeam", status_code=201, response_model=m.Team)
async def create_team(body: m.TeamCreate, p: Principal = Depends(require("write")), store: Store = Depends(get_store),
                      now: datetime = Depends(get_now), key: str | None = Depends(idempotency_header)):
    fp = "createTeam:" + body.model_dump_json()
    if (hit := idem_replay(store, p.user.id, key, fp, now)):
        return hit
    store.validate_schedule(body.open_time, body.close_time)
    t = store.create_team(p.user, body.name, body.timezone, body.office or None, body.open_time, body.close_time, now)
    return created(store, p.user.id, key, fp, now, team_view(t, "admin"),
                   {"Location": f"/v1/teams/{t.id}", "ETag": team_etag(t)})


@router.get("/{teamId}", operation_id="getTeam", response_model=m.Team)
async def get_team(response: Response, ctx: TeamCtx = Depends(team_access("read"))):
    response.headers["ETag"] = team_etag(ctx.team)
    return team_view(ctx.team, ctx.me.role)


@router.patch("/{teamId}", operation_id="updateTeam", response_model=m.Team)
async def update_team(body: m.TeamUpdate, response: Response, ctx: TeamCtx = Depends(team_access("write", admin=True)),
                      if_match: str | None = Depends(if_match_header)):
    t = ctx.team
    check_if_match(if_match, team_etag(t))
    f = body.model_fields_set
    open_time = body.open_time if "open_time" in f else t.open_time
    close_time = body.close_time if "close_time" in f else t.close_time
    ctx.store.validate_schedule(open_time, close_time)
    schedule_changed = (("timezone" in f and body.timezone != t.timezone) or open_time != t.open_time
                        or close_time != t.close_time)
    if "name" in f:
        t.name = body.name  # type: ignore[assignment]
    if "timezone" in f:
        t.timezone = body.timezone  # type: ignore[assignment]
    if "office" in f:
        t.office = body.office or None
    t.open_time, t.close_time = open_time, close_time
    if schedule_changed:
        ctx.store.update_team_schedule(t, ctx.now)
    t.version += 1
    t.updated_at = ctx.now
    ctx.store.emit(t, "team.updated", ctx.now)
    response.headers["ETag"] = team_etag(t)
    return team_view(t, ctx.me.role)
