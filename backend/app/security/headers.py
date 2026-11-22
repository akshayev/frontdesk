"""Security headers + request id middleware and the global error format. Implements:
SECURITY §5, §6, ARCHITECTURE §10 (errors), D-017.

Every response — including 403 csrf, 429 and 500 — carries the SECURITY §5 headers and an
X-Request-ID (uuid4). Every error body is `{error, message, request_id}`. Stack traces are
never sent to clients (in any environment); unhandled exceptions are logged server-side
with the request id so a user-reported id can be found in the logs.
"""

import logging
import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("frontdesk.errors")

SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    (
        "Content-Security-Policy",
        "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
    ),
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
)
HSTS = ("Strict-Transport-Security", "max-age=31536000")

_DEFAULT_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


def request_id_of(scope_or_request: Request | Scope) -> str:
    """The id assigned by SecurityHeadersMiddleware ("-" if the middleware did not run)."""
    scope = scope_or_request.scope if isinstance(scope_or_request, Request) else scope_or_request
    state = scope.get("state") or {}
    return str(state.get("request_id", "-"))


def error_body(scope_or_request: Request | Scope, error: str, message: str) -> dict[str, str]:
    """ARCHITECTURE §10: the one error shape."""
    return {"error": error, "message": message, "request_id": request_id_of(scope_or_request)}


def error_response(
    request: Request | Scope, status: int, error: str, message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """A JSON error response in the standard shape."""
    return JSONResponse(error_body(request, error, message), status_code=status,
                        headers=dict(headers) if headers else None)


class SecurityHeadersMiddleware:
    """Pure ASGI middleware (outermost): request id, SECURITY §5 headers, last-resort 500.

    Catching here (rather than in Starlette's ServerErrorMiddleware, which sits outside all
    user middleware) means even a 500 gets the headers, the request id and the JSON shape.
    """

    def __init__(self, app: ASGIApp, production: bool) -> None:
        self.app = app
        self.headers = SECURITY_HEADERS + ((HSTS,) if production else ())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                for name, value in self.headers:
                    headers[name] = value
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            logger.exception("unhandled error request_id=%s path=%s", request_id, scope["path"])
            if started:
                raise
            response = error_response(
                scope, 500, "internal_error",
                "Something went wrong. Quote the request id if you report it.",
            )
            await response(scope, receive, send_with_headers)


def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """HTTPException → standard shape. `detail` may be {"error", "message"} or a string."""
    assert isinstance(exc, StarletteHTTPException)
    detail: Any = exc.detail
    if isinstance(detail, Mapping) and "error" in detail:
        error, message = str(detail["error"]), str(detail.get("message", ""))
    else:
        error = _DEFAULT_CODES.get(exc.status_code, "error")
        message = str(detail) if detail else error.replace("_", " ")
    return error_response(request, exc.status_code, error, message, exc.headers)


def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    """422 validation_error. Only field locations and messages are returned — never the
    submitted input (it may contain a password)."""
    assert isinstance(exc, RequestValidationError)
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        parts.append(f"{loc}: {err.get('msg', 'invalid')}" if loc else str(err.get("msg")))
    return error_response(request, 422, "validation_error", "; ".join(parts) or "Invalid input.")


def install_error_handlers(app: FastAPI) -> None:
    """Register the global handlers (SECURITY §6)."""
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
