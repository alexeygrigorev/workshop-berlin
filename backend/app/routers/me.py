"""Me: current user, my teams, personal API tokens."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response

from .. import models as m
from ..auth import Principal, get_now, get_store, new_api_token, require
from ..deps import idempotency_header
from ..errors import invalid, not_found
from ..store import Store, TokenRec
from ..views import created, idem_replay, respond, team_ref, user_view

router = APIRouter(prefix="/v1/me", tags=["Me"])
tokens_router = APIRouter(prefix="/v1/me/api-tokens", tags=["API tokens"])


@router.get("", operation_id="getCurrentUser", response_model=m.User)
async def get_current_user(p: Principal = Depends(require("read"))):
    return user_view(p.user)


@router.patch("", operation_id="updateCurrentUser", response_model=m.User)
async def update_current_user(body: m.UserUpdate, p: Principal = Depends(require("write"))):
    p.user.display_name = body.display_name  # type: ignore[assignment]
    return user_view(p.user)


@router.get("/teams", operation_id="listMyTeams", response_model=m.Items)
async def list_my_teams(p: Principal = Depends(require("read")), store: Store = Depends(get_store)):
    items = [m.MyTeam(role=t.members[p.user.id].role, joined_at=t.members[p.user.id].joined_at, team=team_ref(t))
             for t in store.teams_of(p.user.id)]
    items.sort(key=lambda i: (i.joined_at, i.team.name))
    return {"items": [i.model_dump(mode="json") for i in items]}


def _token_view(t: TokenRec) -> m.ApiToken:
    return m.ApiToken(id=t.id, name=t.name, scopes=t.scopes, token_prefix=t.prefix, created_at=t.created_at,
                      expires_at=t.expires_at, last_used_at=t.last_used_at)


@tokens_router.get("", operation_id="listApiTokens", response_model=m.Items)
async def list_api_tokens(p: Principal = Depends(require("read", session_only=True)), store: Store = Depends(get_store)):
    toks = sorted((t for t in store.tokens.values() if t.user_id == p.user.id and t.revoked_at is None),
                  key=lambda t: t.created_at)
    return {"items": [_token_view(t).model_dump(mode="json") for t in toks]}


@tokens_router.post("", operation_id="createApiToken", status_code=201, response_model=m.ApiTokenWithSecret)
async def create_api_token(body: m.ApiTokenCreate, p: Principal = Depends(require("write", session_only=True)),
                           store: Store = Depends(get_store), now: datetime = Depends(get_now),
                           key: str | None = Depends(idempotency_header)):
    fp = "createApiToken:" + body.model_dump_json()
    if (hit := idem_replay(store, p.user.id, key, fp, now)):
        return hit
    if body.expires_at is not None:
        if body.expires_at.tzinfo is None:
            raise invalid("/expires_at", "invalid_format", "expires_at must include a timezone (use UTC `Z`).")
        if body.expires_at <= now:
            raise invalid("/expires_at", "invalid_format", "expires_at must be in the future.")
    t, secret = new_api_token(store, p.user, body.name, list(body.scopes), body.expires_at, now)
    out = m.ApiTokenWithSecret(**_token_view(t).model_dump(), token=secret)
    return created(store, p.user.id, key, fp, now, out)


@tokens_router.delete("/{tokenId}", operation_id="revokeApiToken", status_code=204)
async def revoke_api_token(token_id: UUID = Path(alias="tokenId"),
                           p: Principal = Depends(require("write", session_only=True)),
                           store: Store = Depends(get_store), now: datetime = Depends(get_now)):
    t = store.tokens.get(token_id)
    if not t or t.user_id != p.user.id:
        raise not_found("API token not found.")
    if t.revoked_at is None:
        t.revoked_at = now
    return Response(status_code=204)
