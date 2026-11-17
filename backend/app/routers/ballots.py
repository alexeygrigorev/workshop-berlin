"""Ballots: list, get mine, submit/replace, withdraw."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response

from .. import models as m
from ..deps import TeamCtx, get_poll, team_access
from ..errors import ProblemError, not_found
from ..db.models import Poll
from ..views import ballot_view

router = APIRouter(prefix="/v1/teams/{teamId}/polls/{pollId}/ballots", tags=["Ballots"])


def _assert_accepting(ctx: TeamCtx, p: Poll) -> None:
    if ctx.now < p.opens_at:
        raise ProblemError(409, "poll_not_open", f"Voting opens at {m.fmt_ts(p.opens_at)}.")
    if p.finalized_at is not None or ctx.now >= p.closes_at:
        raise ProblemError(409, "poll_closed", f"Voting closed at {m.fmt_ts(p.closes_at)}.")


@router.get("", operation_id="listBallots", response_model=m.Items)
async def list_ballots(poll_id: UUID = Path(alias="pollId"), ctx: TeamCtx = Depends(team_access("read"))):
    p = get_poll(ctx, poll_id)
    return {"items": [ballot_view(ctx.store, p, b).model_dump(mode="json") for b in ctx.store.sorted_ballots(p)]}


@router.get("/me", operation_id="getMyBallot", response_model=m.Ballot)
async def get_my_ballot(poll_id: UUID = Path(alias="pollId"), ctx: TeamCtx = Depends(team_access("read"))):
    p = get_poll(ctx, poll_id)
    b = p.ballots.get(ctx.principal.user.id)
    if not b:
        raise not_found("You have not voted in this poll.")
    return ballot_view(ctx.store, p, b)


@router.put("/me", operation_id="submitBallot", response_model=m.Ballot)
async def submit_ballot(body: m.BallotSubmit, response: Response, poll_id: UUID = Path(alias="pollId"),
                        ctx: TeamCtx = Depends(team_access("write"))):
    p = get_poll(ctx, poll_id)
    ctx.store.lock_poll(p)  # serialise with finalization; state is re-read under the lock
    _assert_accepting(ctx, p)
    for i, cid in enumerate(body.choices):
        if cid not in p.candidate_ids:
            raise ProblemError(422, "invalid_candidate", f"Restaurant {cid} is not a candidate in this poll.",
                               errors=[{"pointer": f"/choices/{i}", "code": "invalid_candidate",
                                        "message": "Not a candidate in this poll."}])
    uid = ctx.principal.user.id
    ballot, replaced = ctx.store.upsert_ballot(p, uid, body.choices, ctx.now)  # replace = update of the same row
    ctx.store.emit(ctx.team, "ballot.submitted", ctx.now, p.id, user_id=uid, ballot_count=len(p.ballots))
    response.status_code = 200 if replaced else 201
    return ballot_view(ctx.store, p, ballot)


@router.delete("/me", operation_id="deleteMyBallot", status_code=204)
async def delete_my_ballot(poll_id: UUID = Path(alias="pollId"), ctx: TeamCtx = Depends(team_access("write"))):
    p = get_poll(ctx, poll_id)
    ctx.store.lock_poll(p)
    _assert_accepting(ctx, p)
    uid = ctx.principal.user.id
    if p.ballots.pop(uid, None) is not None:
        ctx.store.emit(ctx.team, "ballot.withdrawn", ctx.now, p.id, user_id=uid, ballot_count=len(p.ballots))
    return Response(status_code=204)
