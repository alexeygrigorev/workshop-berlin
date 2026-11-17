"""Password hashing (argon2id), session / personal API tokens, and auth dependencies."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from typing import AsyncIterator

from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool

from .clock import get_clock
from .config import Settings
from .errors import forbidden, unauthenticated
from .db.models import AuthSession, PersonalAccessToken, User
from .store import Store, unit_of_work

SESSION_PREFIX = "wswe_ses_"
PAT_PREFIX = "wswe_pat_"
COOKIE_NAME = "wswe_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Passwords:
    def __init__(self, settings: Settings):
        self.hasher = PasswordHasher(time_cost=settings.argon2_time_cost, memory_cost=settings.argon2_memory_kib,
                                     parallelism=settings.argon2_parallelism)
        self._dummy = self.hasher.hash("dummy-password-for-timing")

    async def hash(self, password: str) -> str:
        return await run_in_threadpool(self.hasher.hash, password)

    async def verify(self, hashed: str | None, password: str) -> bool:
        """Verify; with ``hashed=None`` still burns equivalent time so unknown emails are indistinguishable."""
        def _v() -> bool:
            try:
                return self.hasher.verify(hashed or self._dummy, password) and hashed is not None
            except (VerificationError, InvalidHashError):
                return False
        return await run_in_threadpool(_v)

    def needs_rehash(self, hashed: str) -> bool:
        return self.hasher.check_needs_rehash(hashed)


def new_session(store: Store, user: User, now: datetime, days: int) -> tuple[AuthSession, str]:
    token = SESSION_PREFIX + secrets.token_urlsafe(32)
    s = AuthSession(id=uuid.uuid4(), user_id=user.id, token_hash=sha256(token), created_at=now,
                    expires_at=now + timedelta(days=days), revoked=False)
    store.db.add(s)
    return s, token


def new_api_token(store: Store, user: User, name: str, scopes: list[str], expires_at: datetime | None,
                  now: datetime) -> tuple[PersonalAccessToken, str]:
    token = PAT_PREFIX + secrets.token_urlsafe(30)
    ordered = [s for s in ("read", "write") if s in scopes]
    t = PersonalAccessToken(id=uuid.uuid4(), user_id=user.id, name=name, scopes=ordered, token_hash=sha256(token),
                            prefix=token[:13], created_at=now, expires_at=expires_at)
    store.db.add(t)
    return t, token


@dataclass
class Principal:
    user: User
    kind: str  # "session" | "pat"
    scopes: frozenset[str]
    via_cookie: bool = False
    session: AuthSession | None = None
    token: PersonalAccessToken | None = None


async def get_store(request: Request) -> AsyncIterator[Store]:
    """One transaction per request: committed (then events published) when the handler returns, rolled back on error."""
    with unit_of_work(request.app.state.db, request.app.state.bus) as store:
        yield store


# function scope: the transaction commits right after the handler returns, *before* the response is sent
StoreDep = Depends(get_store, scope="function")


async def get_now(request: Request, clock=Depends(get_clock)) -> datetime:
    return clock.now()


def _bearer(request: Request) -> tuple[str | None, bool]:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer ") and h[7:].strip():
        return h[7:].strip(), False
    c = request.cookies.get(COOKIE_NAME)
    return (c, True) if c else (None, False)


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    settings: Settings = request.app.state.settings
    allowed = {o.rstrip("/") for o in settings.cors_origins}
    allowed.add(f"{request.url.scheme}://{request.headers.get('host', '')}")
    if not origin or origin.rstrip("/") not in allowed:
        raise forbidden("forbidden", "Cookie-authenticated requests must send a matching Origin header.")


def require(scope: str | None, session_only: bool = False) -> Callable:
    """Dependency factory: authenticate, slide the session, and enforce the operation's scope.

    scope=None means no particular scope (e.g. sign-out). session_only rejects personal API tokens
    with 403 insufficient_scope.
    """
    async def dep(request: Request, store: Store = StoreDep, now: datetime = Depends(get_now)) -> Principal:
        token, via_cookie = _bearer(request)
        if not token:
            raise unauthenticated()
        h = sha256(token)
        settings: Settings = request.app.state.settings
        s = store.session_by_hash(h)
        if s is not None:
            if s.revoked or s.expires_at <= now:
                raise unauthenticated("Session expired or revoked. Sign in again.")
            user = store.get_user(s.user_id)
            if not user:
                raise unauthenticated()
            if via_cookie and request.method in UNSAFE:
                _check_origin(request)
            s.expires_at = now + timedelta(days=settings.session_days)  # sliding expiry
            return Principal(user, "session", frozenset({"read", "write"}), via_cookie, session=s)
        if via_cookie:  # the cookie only ever carries session tokens
            raise unauthenticated()
        t = store.token_by_hash(h)
        if t is None:
            raise unauthenticated()
        if t.revoked_at is not None or (t.expires_at is not None and t.expires_at <= now):
            raise unauthenticated("API token expired or revoked.")
        user = store.get_user(t.user_id)
        if not user:
            raise unauthenticated()
        if session_only:
            raise forbidden("insufficient_scope", "This operation requires a session, not a personal API token.")
        if scope and scope not in t.scopes:
            raise forbidden("insufficient_scope", f"This operation requires the `{scope}` scope.")
        t.last_used_at = now
        return Principal(user, "pat", frozenset(t.scopes), token=t)
    return dep
