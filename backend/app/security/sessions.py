"""Cookie sessions, token hash storage, login + lockout, auth dependencies. Implements:
SECURITY §2, §3, D-005, D-016, D-029, AUD-1.

- The session token (32 random bytes, URL-safe) lives only in the HttpOnly cookie
  `fd_session`; the database stores sha256(token), so a DB leak yields no usable session.
- Login always fails with one generic 401 (D-029); failures, lockouts and successes are
  audited. Lockout: 5 failures → locked_until = now + 15 min; the count resets on success.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select, update

from app.audit.chain import append_event
from app.config import Settings
from app.db import RequestContext, Tx
from app.models import ActorType, Agent, AgentRole
from app.models import Session as SessionRow
from app.security.passwords import verify_password

COOKIE_NAME = "fd_session"
SESSION_TTL = timedelta(hours=12)
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)
GENERIC_LOGIN_MESSAGE = "Invalid email or password, or the account is temporarily locked"
_MAX_TOKEN_LEN = 128


def hash_token(token: str) -> bytes:
    """sha256 of the raw cookie token: the only form that is stored (SECURITY §2)."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def create_session(ctx: RequestContext, agent_id: uuid.UUID) -> str:
    """SECURITY §2: new 32-byte token; store its hash with expiry now + 12 h; return token."""
    token = secrets.token_urlsafe(32)
    ctx.session.add(
        SessionRow(
            agent_id=agent_id,
            token_hash=hash_token(token),
            created_at=ctx.now,
            expires_at=ctx.now + SESSION_TTL,
        )
    )
    ctx.session.flush()
    return token


def resolve_session(ctx: RequestContext, token: str | None) -> tuple[SessionRow, Agent] | None:
    """The live session for `token`: exists, not revoked, not expired at the request's now."""
    if not token or len(token) > _MAX_TOKEN_LEN:
        return None
    row = ctx.session.execute(
        select(SessionRow, Agent)
        .join(Agent, Agent.id == SessionRow.agent_id)
        .where(
            SessionRow.token_hash == hash_token(token),
            SessionRow.revoked_at.is_(None),
            SessionRow.expires_at > ctx.now,
        )
    ).one_or_none()
    return None if row is None else (row[0], row[1])


def revoke_session(ctx: RequestContext, session_id: uuid.UUID) -> None:
    """SECURITY §2: logout sets revoked_at (rows are kept, never deleted on logout)."""
    ctx.session.execute(
        update(SessionRow)
        .where(SessionRow.id == session_id, SessionRow.revoked_at.is_(None))
        .values(revoked_at=ctx.now)
    )


def _secure(settings: Settings) -> bool:
    return settings.app_env == "production"


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """D-005: HttpOnly, SameSite=Lax, Path=/, Max-Age 12 h, Secure in production."""
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
        httponly=True,
        samesite="lax",
        secure=_secure(settings),
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Expire the cookie in the browser (same attributes, so the browser matches it)."""
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=_secure(settings)
    )


def _audit_login(
    ctx: RequestContext, agent_id: uuid.UUID | None, event_type: str, payload: dict[str, object]
) -> None:
    append_event(ctx.session, ctx.now, None, ActorType.agent, agent_id, event_type, payload)


def authenticate(ctx: RequestContext, email: str, password: str, ip: str | None) -> Agent | None:
    """SECURITY §2, D-016, D-029: check credentials and apply the DB lockout.

    Returns the agent on success, None on ANY failure (unknown email, wrong password,
    locked) — the caller turns every None into the same 401. A full Argon2 verification runs
    on every path (dummy hash for unknown emails) so timing does not reveal which case it
    was. The agent row is locked FOR UPDATE so concurrent failures count correctly.
    Audited: login_failed (reason), account_locked, login_succeeded (AUD-1).
    """
    email = email.strip().lower()
    base: dict[str, object] = {"email": email, "ip": ip}
    agent = ctx.session.scalars(
        select(Agent).where(Agent.email == email).with_for_update()
    ).one_or_none()
    if agent is None:
        verify_password(None, password)
        _audit_login(ctx, None, "login_failed", {**base, "reason": "unknown_email"})
        return None

    password_ok = verify_password(agent.password_hash, password)
    if agent.locked_until is not None and agent.locked_until > ctx.now:
        _audit_login(ctx, agent.id, "login_failed",
                     {**base, "reason": "locked", "locked_until": agent.locked_until.isoformat()})
        return None
    if not password_ok:
        agent.failed_login_count += 1
        _audit_login(ctx, agent.id, "login_failed",
                     {**base, "reason": "bad_password", "failed_count": agent.failed_login_count})
        if agent.failed_login_count >= MAX_FAILED_LOGINS:
            agent.locked_until = ctx.now + LOCKOUT
            _audit_login(ctx, agent.id, "account_locked",
                         {**base, "failed_count": agent.failed_login_count,
                          "locked_until": agent.locked_until.isoformat()})
        ctx.session.flush()
        return None

    agent.failed_login_count = 0
    agent.locked_until = None
    _audit_login(ctx, agent.id, "login_succeeded", base)
    ctx.session.flush()
    return agent


# --- dependencies (SECURITY §3) -------------------------------------------------------------


@dataclass(frozen=True)
class AgentAuth:
    """The signed-in agent and the session row that authenticated this request."""

    agent: Agent
    session_id: uuid.UUID


def _unauthorized() -> HTTPException:
    return HTTPException(401, detail={"error": "unauthorized", "message": "Sign in required."})


def current_auth(request: Request, ctx: Tx) -> AgentAuth:
    """SECURITY §3: resolve the fd_session cookie or 401."""
    found = resolve_session(ctx, request.cookies.get(COOKIE_NAME))
    if found is None:
        raise _unauthorized()
    session_row, agent = found
    return AgentAuth(agent=agent, session_id=session_row.id)


CurrentAuth = Annotated[AgentAuth, Depends(current_auth)]


def require_agent(auth: CurrentAuth) -> Agent:
    """SECURITY §3: any signed-in agent (agent or lead)."""
    return auth.agent


def require_lead(agent: Annotated[Agent, Depends(require_agent)]) -> Agent:
    """SECURITY §3 / D-006: lead-only endpoints; a plain agent gets 403."""
    if agent.role is not AgentRole.lead:
        raise HTTPException(403, detail={"error": "forbidden", "message": "Lead role required."})
    return agent


CurrentAgent = Annotated[Agent, Depends(require_agent)]
CurrentLead = Annotated[Agent, Depends(require_lead)]
