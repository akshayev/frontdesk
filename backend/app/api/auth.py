"""Login, logout, me. Implements: SECURITY §2, §3, §4, D-005, D-016, D-029."""

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.db import Tx
from app.schemas.agent import AgentOut, LoginIn
from app.security.client_ip import client_ip
from app.security.headers import error_response
from app.security.ratelimit import limit_agent, limit_login
from app.security.sessions import (
    GENERIC_LOGIN_MESSAGE,
    CurrentAgent,
    CurrentAuth,
    authenticate,
    clear_session_cookie,
    create_session,
    revoke_session,
    set_session_cookie,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=AgentOut)
@limit_login
def login(request: Request, body: LoginIn, ctx: Tx) -> Response:
    """D-029: success → session cookie + agent; every failure → the same 401.

    Failures RETURN the 401 (not raise) so the transaction commits the failed-login count,
    the lock and their audit events.
    """
    agent = authenticate(ctx, body.email, body.password, client_ip(request),
                         request.app.state.settings)
    if agent is None:
        return error_response(request, 401, "invalid_credentials", GENERIC_LOGIN_MESSAGE)
    token = create_session(ctx, agent.id)
    response = JSONResponse(AgentOut.model_validate(agent).model_dump(mode="json"))
    set_session_cookie(response, token, request.app.state.settings)
    return response


@router.post("/logout", status_code=204)
@limit_agent
def logout(request: Request, ctx: Tx, auth: CurrentAuth) -> Response:
    """SECURITY §2: revoke this session server-side and clear the cookie."""
    revoke_session(ctx, auth.session_id)
    response = Response(status_code=204)
    clear_session_cookie(response, request.app.state.settings)
    return response


@router.get("/me", response_model=AgentOut)
@limit_agent
def me(request: Request, agent: CurrentAgent) -> AgentOut:
    """The signed-in agent (no password hash, no lockout fields)."""
    return AgentOut.model_validate(agent)
