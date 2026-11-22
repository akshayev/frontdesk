"""Auth and HTTP security on real PostgreSQL: sessions, D-029 login, I-12 lockout, I-13 CSRF,
rate limits, SECURITY §5 headers, error format (SECURITY §2–§6, D-005, D-016, D-017)."""

import hashlib
import re
import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.audit.chain import verify
from app.config import get_settings
from app.main import create_app
from app.models import Agent, AgentRole, AuditEvent, Ticket
from app.models import Session as SessionRow
from app.security.customer_token import CustomerTicket, generate_token, hash_token
from app.security.passwords import hash_password
from app.security.ratelimit import limiter
from app.security.sessions import GENERIC_LOGIN_MESSAGE, CurrentLead, email_hmac
from tests.integration.conftest import migrated_database

PASSWORD = "correct horse battery staple"
CSRF = {"X-Requested-With": "frontdesk"}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


@pytest.fixture(scope="module")
def auth_db() -> Iterator[tuple[Engine, Engine]]:
    with migrated_database("frontdesk_auth_test") as engines:
        yield engines


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> Iterator[None]:
    limiter.reset()
    yield
    limiter.reset()


def _app(auth_db: tuple[Engine, Engine], production: bool = False) -> FastAPI:
    settings = get_settings().model_copy(
        update={"app_env": "production" if production else "development"}
    )
    app = create_app(settings=settings, engine=auth_db[1])

    @app.get("/api/lead/_probe")  # test-only route to exercise require_lead
    def lead_probe(lead: CurrentLead) -> dict[str, str]:
        return {"lead": lead.email}

    @app.get("/api/customer/_probe")  # test-only route to exercise require_customer_ticket
    def customer_probe(ticket: CustomerTicket) -> dict[str, str]:
        return {"ticket": str(ticket.id)}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    # The SPA catch-all (app/spa.py) must stay the last route, after these test-only probes.
    app.router.routes.sort(key=lambda route: getattr(route, "path", "") == "/{path:path}")
    return app


@pytest.fixture
def client(auth_db: tuple[Engine, Engine]) -> TestClient:
    return TestClient(_app(auth_db))


def _agent(auth_db: tuple[Engine, Engine], role: AgentRole = AgentRole.agent) -> str:
    """Insert an agent with PASSWORD; return its (unique) email."""
    email = f"agent-{uuid.uuid4().hex[:10]}@example.com"
    with auth_db[0].begin() as conn:
        conn.execute(
            text("INSERT INTO agents (email, name, role, password_hash, created_at) "
                 "VALUES (:e, 'Test Agent', :r, :h, now())"),
            {"e": email, "r": role.value, "h": hash_password(PASSWORD)},
        )
    return email


def _login(client: TestClient, email: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/auth/login", json={"email": email, "password": password},
                       headers=CSRF)


def _events(auth_db: tuple[Engine, Engine], email: str) -> list[tuple[str, dict[str, object]]]:
    """Login events of a KNOWN account, found by actor_id (D-031: payloads hold no email)."""
    with Session(auth_db[0]) as s:
        agent_id = s.scalars(select(Agent.id).where(Agent.email == email)).one()
        rows = s.scalars(
            select(AuditEvent).where(AuditEvent.actor_id == agent_id).order_by(AuditEvent.id)
        ).all()
        return [(r.event_type, r.payload) for r in rows]


def _body_without_id(resp) -> dict[str, object]:  # type: ignore[no-untyped-def]
    body = dict(resp.json())
    assert UUID_RE.match(body.pop("request_id"))
    return body


# --- sessions and login -----------------------------------------------------------------------


def test_login_success_sets_cookie_with_correct_flags(
    client: TestClient, auth_db: tuple[Engine, Engine]
) -> None:
    """D-005: fd_session HttpOnly, SameSite=Lax, Path=/, Max-Age 12 h; no Secure in dev.
    Only sha256(token) is stored; the response has no password/lock fields."""
    email = _agent(auth_db)
    resp = _login(client, email)
    assert resp.status_code == 200
    assert set(resp.json()) == {"id", "email", "name", "role"}
    cookie = resp.headers["set-cookie"]
    token = re.match(r"fd_session=([^;]+);", cookie).group(1)  # type: ignore[union-attr]
    attrs = {a.strip().lower() for a in cookie.split(";")[1:]}
    assert {"httponly", "samesite=lax", "path=/", "max-age=43200"} <= attrs
    assert "secure" not in attrs
    with Session(auth_db[0]) as s:
        stored = s.scalars(select(SessionRow.token_hash).where(
            SessionRow.agent_id == uuid.UUID(resp.json()["id"]))).one()
        assert bytes(stored) == hashlib.sha256(token.encode()).digest()
    assert [e for e, _ in _events(auth_db, email)] == ["login_succeeded"]
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == email
    assert "password_hash" not in me.text and "locked_until" not in me.text


def test_cookie_is_secure_in_production(auth_db: tuple[Engine, Engine]) -> None:
    client = TestClient(_app(auth_db, production=True), base_url="https://testserver")
    resp = _login(client, _agent(auth_db))
    assert resp.status_code == 200
    attrs = {a.strip().lower() for a in resp.headers["set-cookie"].split(";")[1:]}
    assert "secure" in attrs and "httponly" in attrs


def test_d029_wrong_password_unknown_email_locked_identical_401(
    client: TestClient, auth_db: tuple[Engine, Engine]
) -> None:
    """D-029: the three failure cases return byte-identical bodies (apart from request_id)."""
    email = _agent(auth_db)
    wrong = _login(client, email, "wrong password")
    unknown = _login(client, f"nobody-{uuid.uuid4().hex[:8]}@example.com")
    locked_email = _agent(auth_db)
    with auth_db[0].begin() as conn:
        conn.execute(text("UPDATE agents SET locked_until = now() + interval '10 minutes' "
                          "WHERE email = :e"), {"e": locked_email})
    locked = _login(client, locked_email)  # correct password, but locked
    expected = {"error": "invalid_credentials", "message": GENERIC_LOGIN_MESSAGE}
    for resp in (wrong, unknown, locked):
        assert resp.status_code == 401
        assert _body_without_id(resp) == expected
        assert "set-cookie" not in resp.headers
    assert {k.lower() for k in wrong.headers} == {k.lower() for k in unknown.headers}


def test_i12_lockout_after_five_failures_is_audited(
    client: TestClient, auth_db: tuple[Engine, Engine]
) -> None:
    """I-12 / D-016 / D-029: 5 failures → locked 15 min (even the right password gets the
    generic 401); login_failed ×5 + account_locked + login_failed(locked) audited; after the
    lock expires the right password works and resets the count."""
    email = _agent(auth_db)
    for _ in range(5):
        assert _login(client, email, "wrong").status_code == 401
    limiter.reset()  # the 5/min/IP limit is tested separately
    assert _login(client, email).status_code == 401

    with Session(auth_db[0]) as s:
        count, locked_until, now = s.execute(
            text("SELECT failed_login_count, locked_until, now() FROM agents WHERE email = :e"),
            {"e": email},
        ).one()
    assert count == 5
    assert timedelta(minutes=14) < locked_until - now <= timedelta(minutes=15)

    events = _events(auth_db, email)
    assert [e for e, _ in events] == ["login_failed"] * 5 + ["account_locked", "login_failed"]
    assert [p["reason"] for e, p in events if e == "login_failed"] == ["bad_password"] * 5 + [
        "locked"]
    assert [p["failed_count"] for e, p in events[:5]] == [1, 2, 3, 4, 5]
    assert all(p["ip"] == "testclient" for _, p in events)
    assert all("email" not in p and "email_hmac" not in p for _, p in events)  # D-031

    with auth_db[0].begin() as conn:  # simulate the 15 minutes passing
        conn.execute(text("UPDATE agents SET locked_until = now() - interval '1 second' "
                          "WHERE email = :e"), {"e": email})
    assert _login(client, email).status_code == 200
    with Session(auth_db[0]) as s:
        assert s.execute(text("SELECT failed_login_count, locked_until FROM agents "
                              "WHERE email = :e"), {"e": email}).one() == (0, None)
        assert verify(s).ok  # every login event went through the hash chain


def test_logout_revokes_session(client: TestClient, auth_db: tuple[Engine, Engine]) -> None:
    """SECURITY §2: after logout the old cookie value no longer authenticates."""
    assert _login(client, _agent(auth_db)).status_code == 200
    token = client.cookies.get("fd_session")
    assert client.get("/api/auth/me").status_code == 200
    out = client.post("/api/auth/logout", headers=CSRF)
    assert out.status_code == 204
    assert 'fd_session=""' in out.headers["set-cookie"] or "Max-Age=0" in out.headers["set-cookie"]
    replay = TestClient(client.app, cookies={"fd_session": token})
    resp = replay.get("/api/auth/me")
    assert resp.status_code == 401 and resp.json()["error"] == "unauthorized"
    with Session(auth_db[0]) as s:
        revoked = s.scalars(select(SessionRow.revoked_at).where(
            SessionRow.token_hash == hashlib.sha256(token.encode()).digest())).one()
        assert revoked is not None


def test_me_without_session_is_401(client: TestClient) -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401 and resp.json()["error"] == "unauthorized"
    forged = TestClient(client.app, cookies={"fd_session": "not-a-real-token"})
    assert forged.get("/api/auth/me").status_code == 401


def test_require_lead(client: TestClient, auth_db: tuple[Engine, Engine]) -> None:
    """SECURITY §3: agent → 403 forbidden on a lead route; lead → 200."""
    _login(client, _agent(auth_db))
    resp = client.get("/api/lead/_probe")
    assert resp.status_code == 403 and resp.json()["error"] == "forbidden"
    lead_client = TestClient(client.app)
    lead_email = _agent(auth_db, AgentRole.lead)
    _login(lead_client, lead_email)
    assert lead_client.get("/api/lead/_probe").json() == {"lead": lead_email}


def test_require_customer_ticket_scopes_token_to_one_ticket(
    client: TestClient, auth_db: tuple[Engine, Engine]
) -> None:
    """SECURITY §3 / LEAK-1: token → exactly its ticket (stored as sha256); else 404."""
    token, digest = generate_token()
    assert len(token) >= 43
    assert digest == hash_token(token) == hashlib.sha256(token.encode()).digest()
    ticket_id = uuid.uuid4()
    with auth_db[0].begin() as conn:
        cid = conn.execute(text("INSERT INTO customers (name, email) VALUES ('C', 'c@x.io') "
                                "RETURNING id")).scalar_one()
        conn.execute(text(
            "INSERT INTO tickets (id, subject, customer_id, priority, status, created_at, "
            "first_response_due_at, resolution_due_at, customer_token_hash) "
            "VALUES (:id, 'S', :cid, 'low', 'new', now(), now(), now(), :h)"),
            {"id": ticket_id, "cid": cid, "h": digest})
    ok = client.get("/api/customer/_probe", headers={"X-Ticket-Token": token})
    assert ok.json() == {"ticket": str(ticket_id)}
    for headers in ({"X-Ticket-Token": token[:-1] + "A"}, {}):
        resp = client.get("/api/customer/_probe", headers=headers)
        assert resp.status_code == 404 and resp.json()["error"] == "not_found"
    with Session(auth_db[0]) as s:  # the raw token is not stored anywhere on the ticket
        assert s.get(Ticket, ticket_id).customer_token_hash != token.encode()  # type: ignore[union-attr]


# --- CSRF, rate limits, headers, errors -------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/api/auth/login"), ("post", "/api/auth/logout"),
     ("post", "/api/agent/tickets"), ("patch", "/api/agent/tickets/x/priority"),
     ("delete", "/api/lead/holidays/2026-12-25"), ("post", "/api/lead/tickets/x/assign")],
)
def test_i13_non_get_without_x_requested_with_is_403(
    client: TestClient, method: str, path: str
) -> None:
    """I-13: non-GET under /api/auth, /api/agent, /api/lead without the header → 403 csrf."""
    resp = client.request(method, path, json={})
    assert resp.status_code == 403
    assert _body_without_id(resp)["error"] == "csrf"
    wrong = client.request(method, path, json={}, headers={"X-Requested-With": "XMLHttpRequest"})
    assert wrong.status_code == 403


def test_csrf_header_not_required_for_get(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401  # reaches auth, not csrf


def test_sixth_login_in_a_minute_is_429(client: TestClient, auth_db: tuple[Engine, Engine]) -> None:
    """D-016: login is limited to 5/min per IP; the 6th gets the standard error JSON."""
    email = _agent(auth_db)
    for _ in range(5):
        assert _login(client, email, "wrong").status_code == 401
    resp = _login(client, email)
    assert resp.status_code == 429
    assert _body_without_id(resp)["error"] == "rate_limited"
    assert resp.headers["x-request-id"] == resp.json()["request_id"]


def test_security_headers_present(client: TestClient, auth_db: tuple[Engine, Engine]) -> None:
    """SECURITY §5 on success and error responses; HSTS only in production."""
    for resp in (client.get("/healthz"), client.get("/api/auth/me"),
                 client.post("/api/agent/x", json={})):
        h = resp.headers
        assert h["content-security-policy"] == (
            "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
        assert h["x-frame-options"] == "DENY"
        assert h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"] == "no-referrer"
        assert UUID_RE.match(h["x-request-id"])
        assert "strict-transport-security" not in h
    ids = {client.get("/healthz").headers["x-request-id"] for _ in range(3)}
    assert len(ids) == 3
    prod = TestClient(_app(auth_db, production=True), base_url="https://testserver")
    assert prod.get("/healthz").headers["strict-transport-security"] == "max-age=31536000"


def test_unhandled_error_has_request_id_and_no_traceback(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """SECURITY §6: 500 → {error, message, request_id}; no trace or exception text; the
    exception is logged server-side with the same request id."""
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert set(body) == {"error", "message", "request_id"}
    assert body["error"] == "internal_error"
    assert body["request_id"] == resp.headers["x-request-id"]
    assert "Traceback" not in resp.text and "secret internal detail" not in resp.text
    assert resp.headers["x-frame-options"] == "DENY"
    logged = [r for r in caplog.records if r.name == "frontdesk.errors"]
    assert logged and body["request_id"] in logged[0].getMessage()
    assert logged[0].exc_info is not None


def test_not_found_and_validation_errors_use_standard_shape(client: TestClient) -> None:
    nf = client.get("/api/nope")
    assert nf.status_code == 404 and set(nf.json()) == {"error", "message", "request_id"}
    bad = client.post("/api/auth/login", json={"email": "not-an-email", "password": "hunter2"},
                      headers=CSRF)
    assert bad.status_code == 422 and bad.json()["error"] == "validation_error"
    assert "hunter2" not in bad.text  # submitted input is never echoed


def test_agent_group_limited_per_session(
    client: TestClient, auth_db: tuple[Engine, Engine]
) -> None:
    """D-016: /api/auth/me (agent group) allows 120/min per session; the key is the session
    hash, so a second session from the same IP is unaffected."""
    _login(client, _agent(auth_db))
    other = TestClient(client.app)
    _login(other, _agent(auth_db))
    for _ in range(120):
        assert client.get("/api/auth/me").status_code == 200
    limited = client.get("/api/auth/me")
    assert limited.status_code == 429 and limited.json()["error"] == "rate_limited"
    assert other.get("/api/auth/me").status_code == 200


def test_d031_login_audit_never_stores_the_typed_email(
    client: TestClient, auth_db: tuple[Engine, Engine]
) -> None:
    """D-031: unknown email → only HMAC-SHA256(SESSION_SECRET, lower-cased email) and the IP
    are stored; the typed text (which may be a mistyped password) appears nowhere. The hash
    is stable, so repeated attempts on one address can be correlated."""
    typed = f"  Hunter2-Not-An-Account-{uuid.uuid4().hex[:6]}@Example.com "
    for _ in range(2):
        assert _login(client, typed.strip()).status_code == 401
    expected = email_hmac(typed, get_settings())
    assert expected == email_hmac(typed.strip().lower(), get_settings())
    with Session(auth_db[0]) as s:
        rows = s.scalars(select(AuditEvent).where(
            AuditEvent.payload["email_hmac"].astext == expected)).all()
        assert len(rows) == 2
        for row in rows:
            assert row.payload == {"reason": "unknown_email", "email_hmac": expected,
                                   "ip": "testclient"}
            assert row.actor_id is None
        needle = typed.strip().lower().split("@")[0]
        dump = s.execute(text("SELECT string_agg(payload::text, ' ') FROM audit_events")).scalar()
        assert needle not in dump.lower()  # nowhere in the whole log, in any case
