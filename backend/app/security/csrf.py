"""X-Requested-With header check on non-GET. Implements: SECURITY §1 (CSRF), D-005.

Browsers cannot add a custom header to a cross-site form post or "simple" request, and CORS is
not enabled, so requiring `X-Requested-With: frontdesk` on every state-changing request to
the cookie-authenticated APIs blocks CSRF (SameSite=Lax is the second layer).
"""

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.security.headers import error_response

PROTECTED_PREFIXES = ("/api/auth", "/api/agent", "/api/lead")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
HEADER = "x-requested-with"
EXPECTED = "frontdesk"


def _is_protected(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PROTECTED_PREFIXES)


class CSRFMiddleware:
    """403 {error: "csrf"} for a non-GET request under a protected prefix without the header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] not in SAFE_METHODS
            and _is_protected(scope["path"])
            and Headers(scope=scope).get(HEADER) != EXPECTED
        ):
            response = error_response(scope, 403, "csrf",
                                      "Missing X-Requested-With: frontdesk header.")
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
