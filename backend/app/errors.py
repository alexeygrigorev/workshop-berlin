"""RFC 9457 problem+json errors with the spec's stable codes."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("wswe")

PROBLEM_BASE = "https://docs.wswe.dev/problems/"

TITLES = {
    "unauthenticated": "Not signed in",
    "invalid_credentials": "Invalid login credentials",
    "email_taken": "Email already registered",
    "validation_failed": "Validation failed",
    "not_found": "Not found",
    "not_a_member": "Not a member of this team",
    "admins_only": "Admins only",
    "forbidden": "Forbidden",
    "insufficient_scope": "Insufficient token scope",
    "invite_invalid": "Invalid invite link",
    "last_admin": "Team needs an admin",
    "duplicate_restaurant": "Restaurant already exists",
    "invalid_candidate": "Not a candidate",
    "poll_not_open": "This poll is not open yet",
    "poll_closed": "This poll is closed",
    "poll_not_closable": "Poll is still running",
    "precondition_failed": "Resource changed",
    "idempotency_key_reused": "Idempotency key reused",
    "rate_limited": "Too many requests",
    "unavailable": "Service unavailable",
    "internal_error": "Internal error",
}


class ProblemError(Exception):
    def __init__(self, status: int, code: str, detail: str | None = None, *,
                 errors: list[dict] | None = None, headers: dict | None = None, **extra: Any):
        self.status, self.code, self.detail = status, code, detail
        self.errors, self.headers, self.extra = errors, headers, extra


def problem_response(request: Request, status: int, code: str, detail: str | None = None, *,
                     errors: list[dict] | None = None, headers: dict | None = None, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {
        "type": PROBLEM_BASE + code.replace("_", "-"),
        "title": TITLES.get(code, code),
        "status": status,
        "code": code,
    }
    if detail:
        body["detail"] = detail
    body["instance"] = request.url.path
    if errors:
        body["errors"] = errors
    body.update(extra)
    body["request_id"] = request.headers.get("x-request-id") or uuid.uuid4().hex
    return JSONResponse(body, status_code=status, media_type="application/problem+json", headers=headers)


# Convenience constructors -------------------------------------------------------------------
def unauthenticated(detail="Sign in or provide a valid bearer token."):
    return ProblemError(401, "unauthenticated", detail, headers={"WWW-Authenticate": "Bearer"})


def forbidden(code: str, detail: str | None = None):
    return ProblemError(403, code, detail)


def not_found(detail: str = "Resource not found."):
    return ProblemError(404, "not_found", detail)


def conflict(code: str, detail: str | None = None, **extra):
    return ProblemError(409, code, detail, **extra)


def invalid(pointer: str, code: str, message: str, problem_code: str = "validation_failed", detail: str | None = None):
    return ProblemError(422, problem_code, detail or message,
                        errors=[{"pointer": pointer, "code": code, "message": message}])


_TYPE_TO_CODE = {
    "missing": "required",
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "too_short": "too_short",
    "too_long": "too_many_items",
}
_KNOWN = {"duplicate_items", "invalid_timezone", "invalid_format", "invalid_candidate", "required",
          "too_many_items"}


def _pointer(loc: tuple) -> str:
    where, rest = loc[0], loc[1:]
    if where == "body":
        return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in rest)
    return "?" + ".".join(str(p) for p in rest) if rest else ""


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError):
        return problem_response(request, exc.status, exc.code, exc.detail, errors=exc.errors,
                                headers=exc.headers, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = []
        for e in exc.errors():
            t = e["type"]
            code = t if t in _KNOWN else _TYPE_TO_CODE.get(t, "invalid_format")
            msg = e.get("msg", "Invalid value.")
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, "):]
            errors.append({"pointer": _pointer(tuple(e["loc"])), "code": code, "message": msg})
        detail = errors[0]["message"] if errors else None
        return problem_response(request, 422, "validation_failed", detail, errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found"}.get(exc.status_code)
        if code is None:
            code = "validation_failed" if exc.status_code < 500 else "internal_error"
        return problem_response(request, exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return problem_response(request, 500, "internal_error", "Unexpected server error.")
