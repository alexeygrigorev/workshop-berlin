"""Auth: signUp, signIn, signOut."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response

from .. import models as m
from ..auth import COOKIE_NAME, Passwords, Principal, get_now, get_store, new_session, require
from ..errors import ProblemError
from ..store import Store
from ..views import respond, user_view

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


def _session_response(request: Request, store: Store, user, now: datetime, status: int) -> Response:
    settings = request.app.state.settings
    s, token = new_session(store, user, now, settings.session_days)
    body = m.Session(access_token=token, expires_at=s.expires_at, user=user_view(user))
    resp = respond(body, status)
    resp.set_cookie(COOKIE_NAME, token, max_age=settings.session_days * 86400, httponly=True,
                    secure=settings.cookie_secure, samesite="lax", path="/")
    return resp


@router.post("/sign-up", operation_id="signUp", status_code=201, response_model=m.Session)
async def sign_up(body: m.Credentials, request: Request, store: Store = Depends(get_store),
                  now: datetime = Depends(get_now)):
    if store.user_by_email(body.email):
        raise ProblemError(409, "email_taken", f"An account with {body.email} already exists. Sign in instead.")
    passwords: Passwords = request.app.state.passwords
    user = store.add_user(body.email, await passwords.hash(body.password), now)
    return _session_response(request, store, user, now, 201)


@router.post("/sign-in", operation_id="signIn", response_model=m.Session)
async def sign_in(body: m.Credentials, request: Request, store: Store = Depends(get_store),
                  now: datetime = Depends(get_now)):
    passwords: Passwords = request.app.state.passwords
    user = store.user_by_email(body.email)
    ok = await passwords.verify(user.password_hash if user else None, body.password)
    if not ok or user is None:
        raise ProblemError(401, "invalid_credentials", None)
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = await passwords.hash(body.password)
    return _session_response(request, store, user, now, 200)


@router.post("/sign-out", operation_id="signOut", status_code=204)
async def sign_out(principal: Principal = Depends(require(None))):
    if principal.session is not None:
        principal.session.revoked = True
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp
