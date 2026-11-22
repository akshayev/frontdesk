"""Serve the built React app (ARCHITECTURE §1, §11; D-037). Implements the SPA serving rules:

- `/api/*`, `/healthz` and `/openapi.json` are never swallowed: their routes are registered
  before these catch-alls. An unknown `/api/...` path gets the standard JSON 404 for EVERY
  method (GET, POST, PUT, PATCH, DELETE, …), so all unknown API paths answer the same way. A
  known API path called with the wrong method still gets 405 with an Allow header.
- `/assets/*` are Vite's content-hashed files → `Cache-Control: public, max-age=31536000,
  immutable`. A missing asset is a 404 (never index.html, which would be served as JS).
- Any other GET → a real top-level file if it exists (e.g. favicon), otherwise `index.html`
  (client-side routing), both with `Cache-Control: no-cache` so a new deploy is picked up.

The SECURITY §5 headers (strict CSP) come from SecurityHeadersMiddleware like on every other
response; nothing here changes them.
"""

from collections.abc import Iterable, Iterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.routing import BaseRoute, Match

APP_DIR = Path(__file__).resolve().parent
BUILT_IN = APP_DIR / "static"  # Dockerfile copies frontend/dist here
DEV_DIST = APP_DIR.parents[1] / "frontend" / "dist"  # local `npm run build` output

IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"
RESERVED = ("api", "healthz", "openapi.json")
ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
# Registered last, in this order; tests that add routes later keep these at the end.
FALLBACK_PATHS = ("/api", "/api/{path:path}", "/{path:path}")


def resolve_static_dir(configured: str | None) -> Path | None:
    """The directory holding index.html: STATIC_DIR if set, else app/static, else
    frontend/dist (development). None when no build exists (the API still works)."""
    candidates = [Path(configured)] if configured else [BUILT_IN, DEV_DIST]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


def _inside(root: Path, rel: str) -> Path | None:
    """`root/rel` if it is an existing file inside `root` (no path traversal), else None."""
    if not rel:
        return None
    target = (root / rel).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return None
    return target


def _not_found(message: str) -> HTTPException:
    return HTTPException(404, {"error": "not_found", "message": message})


def _leaf_routes(routes: Iterable[BaseRoute]) -> Iterator[BaseRoute]:
    """Every route, descending into included routers (FastAPI wraps them, keeping the
    original router on `original_router`; its routes carry the full prefixed path)."""
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _leaf_routes(inner.routes)
        else:
            yield route


def _allowed_methods(routes: Iterable[BaseRoute], request: Request) -> set[str]:
    """Methods of the real API routes whose path matches this request (Starlette's PARTIAL
    match = right path, wrong method). Empty → the path is unknown."""
    allowed: set[str] = set()
    for route in _leaf_routes(routes):
        if getattr(route, "path", None) in FALLBACK_PATHS:
            continue
        match, _ = route.matches(request.scope)
        methods = getattr(route, "methods", None)
        if match is Match.PARTIAL and methods:
            allowed |= set(methods)
    return allowed


def install_spa(app: FastAPI, static_dir: Path | None) -> None:
    """Register the API fallback and the SPA catch-all. Must be called after every router."""

    @app.api_route("/api", methods=ALL_METHODS, include_in_schema=False)
    @app.api_route("/api/{path:path}", methods=ALL_METHODS, include_in_schema=False)
    def unknown_api(request: Request) -> Response:
        allowed = _allowed_methods(request.app.router.routes, request)
        if allowed:
            raise HTTPException(405, {"error": "method_not_allowed",
                                      "message": "Method not allowed."},
                                headers={"Allow": ", ".join(sorted(allowed))})
        raise _not_found("No such endpoint.")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(request: Request, path: str) -> Response:
        first = path.split("/", 1)[0]
        if first in RESERVED:
            raise _not_found("No such endpoint.")
        if static_dir is None:
            raise _not_found("The web app is not built.")
        if first == "assets":
            asset = _inside(static_dir, path)
            if asset is None:
                raise _not_found("No such file.")
            return FileResponse(asset, headers={"Cache-Control": IMMUTABLE})
        file = _inside(static_dir, path)
        if file is not None and file.name != "index.html":
            return FileResponse(file, headers={"Cache-Control": NO_CACHE})
        return FileResponse(static_dir / "index.html", media_type="text/html",
                            headers={"Cache-Control": NO_CACHE})
