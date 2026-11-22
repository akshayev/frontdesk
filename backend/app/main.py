"""FastAPI app factory: settings/engine on app.state, routers. Middleware and static mount
are added in later steps (ARCHITECTURE §2)."""

from fastapi import FastAPI
from sqlalchemy import Engine

from app.config import Settings, get_settings


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    """Build the application. Tests pass their own settings / engine (test database)."""
    app = FastAPI(title="Frontdesk")
    app.state.settings = settings or get_settings()
    app.state.engine = engine  # None → built lazily from DATABASE_URL (app.db)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
