"""FastAPI app factory. Routers, middleware and static mount come in later sprints."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build the application."""
    app = FastAPI(title="Frontdesk")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
