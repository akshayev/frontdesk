"""Helpers for API integration tests (see the `api` fixture in conftest.py)."""

import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import RequestContext, get_tx, load_holidays, request_transaction, session_factory
from app.jobs.sweep import SweepResult, run_sweep
from app.main import create_app
from app.models import AgentRole, Ticket
from app.security.sessions import COOKIE_NAME, hash_token

CSRF = {"X-Requested-With": "frontdesk"}
T0 = datetime(2026, 11, 23, 4, 30, tzinfo=UTC)  # Mon 23 Nov 2026 10:00 IST


@dataclass
class Clock:
    """The frozen request time (None → the real DB now())."""

    now: datetime | None = T0

    def advance(self, **delta: float) -> datetime:
        assert self.now is not None
        self.now = self.now + timedelta(**delta)
        return self.now


@dataclass
class AgentHandle:
    """A signed-in agent: its id, name and a TestClient carrying its session + CSRF header."""

    id: uuid.UUID
    name: str
    client: TestClient


@dataclass
class ApiHarness:
    """An app on a throwaway database with controllable time."""

    app: FastAPI
    owner: Engine
    engine: Engine
    clock: Clock = field(default_factory=Clock)

    @classmethod
    def build(cls, owner: Engine, engine: Engine) -> "ApiHarness":
        settings = get_settings().model_copy(update={"app_env": "development",
                                                     "sweep_enabled": False})
        app = create_app(settings=settings, engine=engine)
        harness = cls(app=app, owner=owner, engine=engine)

        def frozen_tx(request: Request) -> Iterator[RequestContext]:
            with request_transaction(session_factory(request.app)) as ctx:
                now = harness.clock.now or ctx.now
                yield RequestContext(now=now, session=ctx.session)

        app.dependency_overrides[get_tx] = frozen_tx
        return harness

    def agent(self, name: str, role: AgentRole = AgentRole.agent) -> AgentHandle:
        """Create an agent and sign it in (session row inserted directly)."""
        token = secrets.token_urlsafe(32)
        email = f"{name.lower()}-{uuid.uuid4().hex[:8]}@arvo.example"
        with self.owner.begin() as conn:
            agent_id = conn.execute(text(
                "INSERT INTO agents (email, name, role, password_hash, created_at) "
                "VALUES (:e, :n, :r, 'x', :t) RETURNING id"),
                {"e": email, "n": name, "r": role.value, "t": T0}).scalar_one()
            conn.execute(text(
                "INSERT INTO sessions (agent_id, token_hash, created_at, expires_at) "
                "VALUES (:a, :h, :t, :x)"),
                {"a": agent_id, "h": hash_token(token), "t": T0,
                 "x": datetime(2030, 1, 1, tzinfo=UTC)})
        client = TestClient(self.app, headers=CSRF, cookies={COOKIE_NAME: token})
        return AgentHandle(id=agent_id, name=name, client=client)

    def public_ticket(self, subject: str = "Login fails", priority: str = "medium",
                      email: str | None = None, description: str = "I cannot log in."
                      ) -> tuple[uuid.UUID, str]:
        """IN-1 through the public API → (ticket id, raw customer token)."""
        resp = TestClient(self.app).post("/api/public/tickets", json={
            "name": "Asha Rao", "email": email or f"asha-{uuid.uuid4().hex[:6]}@example.com",
            "subject": subject, "description": description, "priority": priority})
        assert resp.status_code == 201, resp.text
        token = resp.json()["customer_link"].split("/t#", 1)[1]
        return self.ticket_id(resp.json()["number"]), token

    def customer(self, token: str) -> TestClient:
        return TestClient(self.app, headers={"X-Ticket-Token": token})

    def ticket_id(self, number: int) -> uuid.UUID:
        with Session(self.owner) as s:
            return s.scalars(select(Ticket.id).where(Ticket.number == number)).one()

    def ticket(self, ticket_id: uuid.UUID) -> Ticket:
        with Session(self.owner, expire_on_commit=False) as s:
            ticket = s.get(Ticket, ticket_id)
            assert ticket is not None
            return ticket

    def sweep(self) -> SweepResult:
        """Run the auto-close sweep at the frozen time, as the app role."""
        assert self.clock.now is not None
        with Session(self.engine) as s, s.begin():
            return run_sweep(s, self.clock.now, load_holidays(s))

    def version(self, agent: AgentHandle, ticket_id: uuid.UUID) -> int:
        resp = agent.client.get(f"/api/agent/tickets/{ticket_id}")
        assert resp.status_code == 200, resp.text
        return int(resp.json()["version"])
