"""slowapi rate-limit groups. Implements: SECURITY §4, D-016, D-032.

In-memory, single process (limitation in SECURITY §7). Decorate every endpoint with exactly
one group; the endpoint must take `request: Request`.
- limit_login     5/min per client IP                    (POST /api/auth/login)
- limit_customer  30/min per client IP, shared scope     (/api/customer/*)
- limit_public    30/min per client IP, shared scope     (/api/public/*)
  (customer and public are separate buckets on purpose, D-032)
- limit_agent     120/min per session, shared scope      (/api/agent/*, /api/lead/*, and the
                  session endpoints /api/auth/logout, /api/auth/me) — keyed by sha256 of the
                  session cookie, falling back to the IP when there is no cookie.
"""

import hashlib

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.security.headers import error_response
from app.security.sessions import COOKIE_NAME

LOGIN_LIMIT = "5/minute"
CUSTOMER_LIMIT = "30/minute"
PUBLIC_LIMIT = "30/minute"
AGENT_LIMIT = "120/minute"


def client_ip(request: Request) -> str:
    """Client address (uvicorn --proxy-headers resolves X-Forwarded-For on Render, §12)."""
    return get_remote_address(request)


def session_key(request: Request) -> str:
    """Agent/lead limit key: hash of the session token (never the token itself)."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return "s:" + hashlib.sha256(token.encode("utf-8")).hexdigest()
    return "ip:" + client_ip(request)


limiter = Limiter(key_func=client_ip, storage_uri="memory://", headers_enabled=False)

limit_login = limiter.limit(LOGIN_LIMIT, key_func=client_ip)
limit_customer = limiter.shared_limit(CUSTOMER_LIMIT, scope="customer", key_func=client_ip)
limit_public = limiter.shared_limit(PUBLIC_LIMIT, scope="public", key_func=client_ip)
limit_agent = limiter.shared_limit(AGENT_LIMIT, scope="agent", key_func=session_key)


def _rate_limited(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitExceeded)
    return error_response(request, 429, "rate_limited", "Too many requests. Try again shortly.",
                          {"Retry-After": "60"})


def install_rate_limiting(app: FastAPI) -> None:
    """Attach the limiter and the 429 handler (standard error JSON)."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limited)
