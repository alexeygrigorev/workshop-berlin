"""streamTeamEvents: Server-Sent Events for one team."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from ..deps import TeamCtx, team_access
from ..events import event_stream

router = APIRouter(prefix="/v1/teams/{teamId}/events", tags=["Events"])


@router.get("", operation_id="streamTeamEvents", response_class=StreamingResponse,
            responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}})
async def stream_team_events(request: Request, ctx: TeamCtx = Depends(team_access("read")),
                             last_event_id: str | None = Header(default=None, alias="Last-Event-ID")):
    # The request transaction is already closed when streaming starts, so membership is re-checked with short
    # transactions of its own.
    app, team_id, uid = request.app, ctx.team.id, ctx.principal.user.id

    def is_member() -> bool:
        with app.state.uow() as store:
            return store.is_member(team_id, uid)

    gen = event_stream(app.state.bus, team_id, uid, last_event_id, is_member, lambda: request.app.state.clock.now(),
                       keepalive_seconds=25.0)
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
