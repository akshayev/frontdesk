"""FastAPI app factory: settings/engine on app.state, middleware, error handlers, routers.
The static SPA mount and the sweep lifespan come in later sprints (ARCHITECTURE §2)."""

from fastapi import FastAPI
from sqlalchemy import Engine

from app.api import auth
from app.config import Settings, get_settings
from app.security.csrf import CSRFMiddleware
from app.security.headers import SecurityHeadersMiddleware, install_error_handlers
from app.security.ratelimit import install_rate_limiting


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    """Build the application. Tests pass their own settings / engine (test database)."""
    settings = settings or get_settings()
    production = settings.app_env == "production"
    app = FastAPI(
        title="Frontdesk",
        docs_url=None if production else "/docs",
        redoc_url=None,
        openapi_url=None if production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = engine  # None → built lazily from DATABASE_URL (app.db)

    install_error_handlers(app)
    install_rate_limiting(app)
    # Last added = outermost: SecurityHeaders wraps CSRF so a 403 csrf also gets headers.
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, production=production)

    app.include_router(auth.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
