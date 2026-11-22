"""DomainError → the standard error JSON (ARCHITECTURE §10). Implements: CLM-1, CLM-3.

Body: {error, message, request_id, **extra} — e.g. already_claimed adds `owner`, stale_version
adds `current_version`. `extra` can never overwrite the three standard keys.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.tickets import DomainError
from app.security.headers import error_body


def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    body = {**exc.extra, **error_body(request, exc.code, exc.message)}
    return JSONResponse(body, status_code=exc.http_status)


def install_domain_errors(app: FastAPI) -> None:
    """Register the DomainError handler."""
    app.add_exception_handler(DomainError, _domain_error)
