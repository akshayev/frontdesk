"""FastAPI app factory: settings/engine on app.state, middleware, error handlers, routers, and
the lifespan that runs the auto-close sweep loop (ARCHITECTURE §2, §9), and — registered last —
the catch-all that serves the built React app (app/spa.py).

Request path, outermost first:
  1. SecurityHeadersMiddleware — assigns the request id, adds the SECURITY §5 headers to every
     response (including 403 csrf, 429, 500) and turns unhandled errors into a JSON 500.
  2. CSRFMiddleware — non-GET under /api/auth, /api/agent, /api/lead without
     `X-Requested-With: frontdesk` → 403 before any endpoint code or DB work runs.
  3. Rate limiter — slowapi decorators on each endpoint (one group per endpoint, SECURITY §4);
     they run inside routing, after the two middlewares, and raise 429 in the standard shape.
  4. Endpoint dependencies — one DB transaction + DB now per request (app.db.Tx), then auth.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, Response
from sqlalchemy import Engine

from app.api import agent, auth, customer, lead, public
from app.api.errors import install_domain_errors
from app.config import Settings, get_settings
from app.db import session_factory
from app.jobs.sweep import sweep_loop
from app.security.csrf import CSRFMiddleware
from app.security.headers import SecurityHeadersMiddleware, install_error_handlers
from app.security.ratelimit import install_rate_limiting
from app.spa import install_spa, resolve_static_dir


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """ARCHITECTURE §9: start the sweep loop (once now, then every 5 min) unless
    SWEEP_ENABLED=false (tests); cancel it on shutdown."""
    task: asyncio.Task[None] | None = None
    if app.state.settings.sweep_enabled:
        task = asyncio.create_task(sweep_loop(lambda: session_factory(app)))
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    """Build the application. Tests pass their own settings / engine (test database)."""
    settings = settings or get_settings()
    production = settings.app_env == "production"
    app = FastAPI(
        title="Frontdesk",
        # D-035: Swagger UI (third-party scripts) only outside production; the read-only
        # schema /openapi.json is served everywhere so evaluators can load it in any viewer.
        docs_url=None if production else "/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine  # None → built lazily from DATABASE_URL (app.db)

    install_error_handlers(app)
    install_domain_errors(app)
    install_rate_limiting(app)
    # Last added = outermost: SecurityHeaders wraps CSRF so a 403 csrf also gets headers.
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, production=production)

    for module in (auth, agent, lead, customer, public):
        app.include_router(module.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Uptime monitors send HEAD by default; kept out of the schema (same endpoint as GET).
    @app.head("/healthz", include_in_schema=False)
    def healthz_head() -> Response:
        return Response(status_code=200)

    # Last: every API route above wins over the SPA catch-all.
    install_spa(app, resolve_static_dir(settings.static_dir))
    return app


app = create_app()
