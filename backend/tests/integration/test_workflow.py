"""Ticket workflow through the HTTP API on PostgreSQL with controlled time (TEST-PLAN I-8, I-9,
I-10, I-11; D-026, D-027, PRI-5, RPT-1, AUD-3)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AgentRole, AuditEvent, CloseReason, TicketStatus
from app.sla.calendar import add_working_minutes
from tests.integration.api_support import T0, AgentHandle, ApiHarness


def ist(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    """An IST wall-clock time as an aware UTC datetime."""
    return datetime(y, mo, d, h, mi, tzinfo=UTC) - timedelta(hours=5, minutes=30)


def _claimed(api: ApiHarness, agent: AgentHandle, **kw: str) -> tuple[uuid.UUID, str]:
    tid, token = api.public_ticket(**kw)
    assert agent.client.post(f"/api/agent/tickets/{tid}/claim").status_code == 200
    return tid, token


def _reply(api: ApiHarness, agent: AgentHandle, tid: uuid.UUID, wait: bool = False,
           body: str = "Here is what we found.") -> dict:
    resp = agent.client.post(f"/api/agent/tickets/{tid}/replies", json={
        "body": body, "expected_version": api.version(agent, tid), "wait_for_customer": wait})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _resolve(api: ApiHarness, agent: AgentHandle, tid: uuid.UUID) -> dict:
    resp = agent.client.post(f"/api/agent/tickets/{tid}/resolve",
                             json={"expected_version": api.version(agent, tid)})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _in_state(api: ApiHarness, owner: AgentHandle, state: TicketStatus) -> tuple[uuid.UUID, str]:
    """A fresh ticket owned by `owner` (except `new`) in the given state."""
    if state is TicketStatus.new:
        return api.public_ticket()
    tid, token = _claimed(api, owner)
    if state is TicketStatus.waiting_on_customer:
        _reply(api, owner, tid, wait=True)
    elif state in (TicketStatus.resolved, TicketStatus.closed):
        _reply(api, owner, tid)
        _resolve(api, owner, tid)
        if state is TicketStatus.closed:
            saved = api.clock.now
            api.clock.advance(days=8)
            api.sweep()
            api.clock.now = saved
    assert api.ticket(tid).status is state
    return tid, token


# --- I-8 ---------------------------------------------------------------------------------------

S = TicketStatus
Attempt = Callable[[ApiHarness, dict[str, AgentHandle], uuid.UUID, str], object]


def _agent_call(actor: str, method: str, suffix: str, extra: dict | None = None) -> Attempt:
    def call(api: ApiHarness, agents: dict[str, AgentHandle], tid: uuid.UUID, _t: str):
        version = api.version(agents["owner"], tid)
        body = {"expected_version": version, **(extra or {})}
        if suffix == "assign":
            body["agent_id"] = str(agents["other"].id)
            return agents[actor].client.post(f"/api/lead/tickets/{tid}/assign", json=body)
        if suffix == "claim":
            return agents[actor].client.post(f"/api/agent/tickets/{tid}/claim")
        return getattr(agents[actor].client, method)(f"/api/agent/tickets/{tid}/{suffix}",
                                                     json=body)
    return call


def _customer_reopen(api: ApiHarness, _a: dict[str, AgentHandle], _tid: uuid.UUID, token: str):
    return api.customer(token).post("/api/customer/ticket/reopen")


REPLY = _agent_call("owner", "post", "replies", {"body": "hello"})
WAIT = _agent_call("owner", "post", "replies", {"body": "hello", "wait_for_customer": True})
RESOLVE = _agent_call("owner", "post", "resolve")
RELEASE = _agent_call("owner", "post", "release")
PRIORITY = _agent_call("owner", "patch", "priority", {"priority": "urgent"})
CLAIM_OTHER = _agent_call("other", "post", "claim")
ASSIGN = _agent_call("lead", "post", "assign")

# Every (status, action) pair the ARCHITECTURE §4 table does not contain. ("claim" of a ticket
# someone owns in new/open/waiting is CLM-1's 409 already_claimed, tested in I-1.)
ILLEGAL: list[tuple[TicketStatus, str, Attempt]] = [
    (S.new, "reply", REPLY), (S.new, "reply+wait", WAIT), (S.new, "resolve", RESOLVE),
    (S.new, "release", RELEASE), (S.new, "customer reopen", _customer_reopen),
    (S.open, "customer reopen", _customer_reopen),
    (S.waiting_on_customer, "reply", REPLY), (S.waiting_on_customer, "resolve", RESOLVE),
    (S.waiting_on_customer, "release", RELEASE),
    (S.waiting_on_customer, "customer reopen", _customer_reopen),
    (S.resolved, "reply", REPLY), (S.resolved, "resolve", RESOLVE),
    (S.resolved, "release", RELEASE), (S.resolved, "change priority", PRIORITY),
    (S.resolved, "claim", CLAIM_OTHER),
    (S.closed, "reply", REPLY), (S.closed, "resolve", RESOLVE), (S.closed, "release", RELEASE),
    (S.closed, "change priority", PRIORITY), (S.closed, "claim", CLAIM_OTHER),
    (S.closed, "assign", ASSIGN), (S.closed, "customer reopen", _customer_reopen),
]


@pytest.mark.parametrize(("state", "action", "attempt"), ILLEGAL,
                         ids=[f"{s.value}-{a}" for s, a, _ in ILLEGAL])
def test_i8_illegal_transitions_are_409(api: ApiHarness, state: TicketStatus, action: str,
                                        attempt: Attempt) -> None:
    agents = {"owner": api.agent("Owner"), "other": api.agent("Other"),
              "lead": api.agent("Lead", AgentRole.lead)}
    tid, token = _in_state(api, agents["owner"], state)
    before = api.ticket(tid).version
    resp = attempt(api, agents, tid, token)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] == "illegal_transition"
    assert api.ticket(tid).version == before


# --- I-9, I-10, I-11, D-027, PRI-5 ---------------------------------------------------------------


def test_i9_customer_reply_to_waiting_resumes_clock(api: ApiHarness) -> None:
    """WAIT-3 / D-026: status open; resolution due = old due + working minutes waited.
    Medium created Mon 10:00 → resolution due Thu 26 Nov 10:00. Paused Mon 10:30, customer
    replies Tue 10:00: waited 480 + 30 = 510 working min → due Thu 26 Nov 18:30 IST."""
    agent = api.agent("Priya")
    tid, token = _claimed(api, agent)
    assert api.ticket(tid).resolution_due_at == ist(2026, 11, 26, 10, 0)
    api.clock.now = ist(2026, 11, 23, 10, 30)
    detail = _reply(api, agent, tid, wait=True)
    assert detail["ticket"]["status"] == "waiting_on_customer"
    assert detail["badge"]["state"] in ("on_track", "paused")
    api.clock.now = ist(2026, 11, 24, 10, 0)
    assert api.customer(token).post("/api/customer/ticket/messages",
                                    json={"body": "Here is the screenshot"}).status_code == 201
    ticket = api.ticket(tid)
    assert ticket.status is S.open and ticket.paused_at is None
    assert ticket.resolution_due_at == add_working_minutes(ist(2026, 11, 26, 10, 0), 510,
                                                           frozenset())
    assert ticket.resolution_due_at == ist(2026, 11, 26, 18, 30)
    events = [e["event_type"] for e in agent.client.get(f"/api/agent/tickets/{tid}")
              .json()["events"]]
    assert events[-2:] == ["customer_message", "status_changed"]


def test_i10_customer_writes_to_closed_ticket_gets_new_ticket(api: ApiHarness) -> None:
    """RO-4 / D-012: a NEW ticket (Re: subject, same priority, parent_ticket_id = old) with its
    own link; the old ticket stays closed and unchanged."""
    agent = api.agent("Arjun")
    old_id, old_token = _in_state(api, agent, S.closed)
    old_version = api.ticket(old_id).version
    api.clock.advance(days=9)
    resp = api.customer(old_token).post("/api/customer/ticket/messages",
                                        json={"body": "It is broken again"})
    assert resp.status_code == 201
    out = resp.json()
    new_token = out["new_ticket_link"].split("/t#", 1)[1]
    assert new_token != old_token
    new_view = api.customer(new_token).get("/api/customer/ticket").json()
    assert new_view["number"] == out["new_ticket_number"]
    assert new_view["subject"] == "Re: Login fails" and new_view["status"] == "new"
    assert [m["body"] for m in new_view["messages"]] == ["It is broken again"]
    child = api.ticket(api.ticket_id(out["new_ticket_number"]))
    assert child.parent_ticket_id == old_id
    assert child.priority == api.ticket(old_id).priority
    old = api.ticket(old_id)
    assert (old.status, old.version) == (S.closed, old_version)
    old_view = api.customer(old_token).get("/api/customer/ticket").json()
    assert old_view["message_starts_new_ticket"] is True
    assert "It is broken again" not in [m["body"] for m in old_view["messages"]]


def test_i11_sweep_auto_closes_silent_waiting_and_expired_resolved(api: ApiHarness) -> None:
    """WAIT-4 / D-025: closes at exactly 2700 working minutes of silence (not 2699), actor
    system. RO-3: resolved closes at exactly 7 calendar days (not 1 s before)."""
    agent = api.agent("Kavya")
    api.clock.now = ist(2026, 11, 23, 10, 30)
    waiting, _ = _in_state(api, agent, S.waiting_on_customer)
    paused = api.ticket(waiting).paused_at
    assert paused is not None
    api.clock.now = ist(2026, 11, 25, 15, 0)  # resolved two days later (Wed)
    resolved, _ = _in_state(api, agent, S.resolved)
    resolved_at = api.ticket(resolved).resolved_at
    assert resolved_at is not None

    api.clock.now = add_working_minutes(paused, 2699, frozenset())
    api.sweep()
    assert api.ticket(waiting).status is S.waiting_on_customer
    api.clock.now = add_working_minutes(paused, 2700, frozenset())
    assert api.clock.now == ist(2026, 11, 30, 10, 30)  # 5 working days later
    api.sweep()
    closed = api.ticket(waiting)
    assert (closed.status, closed.close_reason) == (S.closed, CloseReason.no_customer_reply)
    assert closed.closed_at == api.clock.now

    api.clock.now = resolved_at + timedelta(days=7) - timedelta(seconds=1)
    api.sweep()
    assert api.ticket(resolved).status is S.resolved
    api.clock.now = resolved_at + timedelta(days=7)
    api.sweep()
    assert api.ticket(resolved).close_reason is CloseReason.reopen_window_expired
    api.sweep()  # idempotent

    with Session(api.owner) as s:
        for tid, reason in ((waiting, "no_customer_reply"), (resolved, "reopen_window_expired")):
            rows = s.scalars(select(AuditEvent).where(AuditEvent.ticket_id == tid)
                             .order_by(AuditEvent.id)).all()
            closing = [r for r in rows if r.event_type == "auto_closed"]
            assert len(closing) == 1 and closing[0].payload == {"reason": reason}
            assert closing[0].actor_type.value == "system" and closing[0].actor_id is None
            assert rows[-1].event_type == "status_changed" and rows[-1].payload["to"] == "closed"


def test_d027_resolve_without_reply_is_409_reply_required(api: ApiHarness) -> None:
    agent = api.agent("Rahul")
    tid, _ = _claimed(api, agent)
    resp = agent.client.post(f"/api/agent/tickets/{tid}/resolve",
                             json={"expected_version": api.version(agent, tid)})
    assert resp.status_code == 409 and resp.json()["error"] == "reply_required"
    assert "resolve" not in agent.client.get(f"/api/agent/tickets/{tid}").json()[
        "allowed_actions"]
    _reply(api, agent, tid)
    assert _resolve(api, agent, tid)["ticket"]["status"] == "resolved"


def test_pri5_priority_change_audit_payload(api: ApiHarness) -> None:
    """PRI-5 + D-008 example: medium created Mon 10:00 (response due 14:30), upgraded to urgent
    at 10:30 → response due 12:30, resolution due min(Thu 10:00, Tue 10:30) = Tue 10:30."""
    agent = api.agent("Ananya")
    tid, _ = _claimed(api, agent)
    api.clock.now = ist(2026, 11, 23, 10, 30)
    resp = agent.client.patch(f"/api/agent/tickets/{tid}/priority", json={
        "priority": "urgent", "expected_version": api.version(agent, tid)})
    assert resp.status_code == 200, resp.text
    event = resp.json()["events"][-1]
    assert event["event_type"] == "priority_changed"
    assert event["actor_name"] == "Ananya"

    def at(value: str) -> datetime:
        return datetime.fromisoformat(value)

    payload = event["payload"]
    assert (payload["from"], payload["to"]) == ("medium", "urgent")
    assert at(payload["old_response_due"]) == ist(2026, 11, 23, 14, 30)
    assert at(payload["new_response_due"]) == ist(2026, 11, 23, 12, 30)
    assert at(payload["old_resolution_due"]) == ist(2026, 11, 26, 10, 0)
    assert at(payload["new_resolution_due"]) == ist(2026, 11, 24, 10, 30)
    ticket = api.ticket(tid)
    assert ticket.first_response_due_at == ist(2026, 11, 23, 12, 30)
    assert ticket.resolution_due_at == ist(2026, 11, 24, 10, 30)
    assert set(payload) == {"from", "to", "old_response_due", "new_response_due",
                            "old_resolution_due", "new_resolution_due"}


# --- RPT-1 -----------------------------------------------------------------------------------


def test_rpt1_late_report_numbers(api: ApiHarness) -> None:
    """Hand-built scenario (all IST, Mon 23 Nov 2026, no holidays in range):
    - Mon 10:00 medium ticket created (response due 14:30, resolution due Thu 10:00).
    - Mon 10:30 upgraded to urgent → response due 12:30, resolution due Tue 10:30 (PRI-1).
    - Mon 13:00 reply + wait → response met 30 working min late; 390 working min remain.
    - Tue 11:00 customer replies → waited 330 + 90 = 420 working min; due Tue 17:30 (D-026).
    - Wed 10:30 resolved → resolution 60 + 60 = 120 working min late.
    Expected row: initial medium, current urgent, one change, response late 30, resolution
    late 120, waiting on customer 420. A ticket handled on time is not in the report."""
    agent, lead = api.agent("Vikram"), api.agent("Meera", AgentRole.lead)
    on_time, _ = _claimed(api, agent, subject="Fine one")
    tid, token = _claimed(api, agent, subject="=SUM(A1:A9)")
    _reply(api, agent, on_time)
    api.clock.now = ist(2026, 11, 23, 10, 30)
    agent.client.patch(f"/api/agent/tickets/{tid}/priority", json={
        "priority": "urgent", "expected_version": api.version(agent, tid)})
    api.clock.now = ist(2026, 11, 23, 13, 0)
    _reply(api, agent, tid, wait=True)
    api.clock.now = ist(2026, 11, 24, 11, 0)
    api.customer(token).post("/api/customer/ticket/messages", json={"body": "Done, retry?"})
    assert api.ticket(tid).resolution_due_at == ist(2026, 11, 24, 17, 30)
    api.clock.now = ist(2026, 11, 25, 10, 30)
    _resolve(api, agent, tid)
    _resolve(api, agent, on_time)
    api.clock.now = ist(2026, 11, 25, 11, 0)

    rows = lead.client.get("/api/lead/reports/late").json()
    assert str(on_time) not in [r["ticket_id"] for r in rows]
    row = next(r for r in rows if r["ticket_id"] == str(tid))
    assert row["assignee"]["name"] == "Vikram"
    assert (row["initial_priority"], row["current_priority"]) == ("medium", "urgent")
    assert [(h["from_priority"], h["to_priority"]) for h in row["priority_history"]] == [
        ("medium", "urgent")]
    assert datetime.fromisoformat(row["priority_history"][0]["at"]) == ist(2026, 11, 23, 10, 30)
    missed = {m["target"]: m["working_minutes_late"] for m in row["missed"]}
    assert missed == {"response": 30, "resolution": 120}
    assert row["waiting_on_customer_working_minutes"] == 420

    csv = lead.client.get("/api/lead/reports/late.csv")
    assert csv.headers["content-disposition"] == 'attachment; filename="late-tickets.csv"'
    line = next(x for x in csv.text.splitlines() if x.startswith(f"FD-{api.ticket(tid).number},"))
    assert line.split(",")[1] == "'=SUM(A1:A9)"  # formula-injection guard
    assert line.endswith(",30,120,420")
    assert "medium->urgent" in line
    assert agent.client.get("/api/lead/reports/late").status_code == 403


def test_transcript_csv_guard_and_public_messages_only(api: ApiHarness) -> None:
    agent = api.agent("Sneha")
    tid, _ = _claimed(api, agent, description="@SUM(1+1)*cmd|' /C calc'!A0")
    v = api.version(agent, tid)
    agent.client.post(f"/api/agent/tickets/{tid}/notes",
                      json={"body": "internal only", "expected_version": v})
    api.clock.advance(minutes=5)
    _reply(api, agent, tid, body="-2+3")
    resp = agent.client.get(f"/api/agent/tickets/{tid}/transcript.csv")
    lines = resp.text.splitlines()
    assert lines[0] == "time_ist,author,message"
    assert lines[1].endswith(",Customer: Asha Rao,'@SUM(1+1)*cmd|' /C calc'!A0")
    assert lines[1].startswith("2026-11-23T10:00:00+05:30")
    assert lines[2].endswith(",Support: Sneha,'-2+3")
    assert "internal only" not in resp.text and len(lines) == 3


# --- full workflow ---------------------------------------------------------------------------


def test_full_workflow_then_audit_verify_ok(api: ApiHarness) -> None:
    """Every action type through the API, then AUD-3 verify over the whole chain."""
    a, b = api.agent("Karthik"), api.agent("Divya")
    lead = api.agent("Meera", AgentRole.lead)
    t1, tok1 = api.public_ticket(priority="low")
    created = a.client.post("/api/agent/tickets", json={
        "customer_name": "Ravi", "customer_email": "ravi@example.com", "subject": "VPN",
        "body": "VPN down since morning", "priority": "urgent"}).json()
    t2, tok2 = uuid.UUID(created["id"]), created["customer_link"].split("/t#", 1)[1]
    a.client.post(f"/api/agent/tickets/{t1}/claim")
    b.client.post(f"/api/agent/tickets/{t1}/notes", json={
        "body": "check the proxy", "expected_version": api.version(a, t1)})
    _reply(api, a, t1, wait=True)
    api.clock.advance(hours=2)
    api.customer(tok1).post("/api/customer/ticket/messages", json={"body": "still broken"})
    a.client.post(f"/api/agent/tickets/{t1}/release",
                  json={"expected_version": api.version(a, t1)})
    lead.client.post(f"/api/lead/tickets/{t1}/assign", json={
        "agent_id": str(b.id), "expected_version": api.version(lead, t1)})
    lead.client.patch(f"/api/agent/tickets/{t1}/priority", json={
        "priority": "medium", "expected_version": api.version(lead, t1)})
    _reply(api, b, t1)
    _resolve(api, b, t1)
    api.customer(tok1).post("/api/customer/ticket/reopen")
    _resolve(api, b, t1)
    lead.client.post(f"/api/lead/tickets/{t2}/assign", json={
        "agent_id": str(a.id), "expected_version": api.version(lead, t2)})
    _reply(api, a, t2)
    _resolve(api, a, t2)
    lead.client.post("/api/lead/holidays", json={"date": "2027-03-14", "name": "Holi"})
    lead.client.delete("/api/lead/holidays/2027-03-14")
    api.clock.advance(days=8)
    api.sweep()
    out = api.customer(tok2).post("/api/customer/ticket/messages", json={"body": "again"}).json()
    assert out["new_ticket_link"]
    assert api.ticket(t1).status is S.closed and api.ticket(t2).status is S.closed

    result = lead.client.get("/api/lead/audit/verify").json()
    with api.owner.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
        types = set(conn.execute(text("SELECT DISTINCT event_type FROM audit_events")).scalars())
    assert result == {"ok": True, "checked": total, "first_bad_id": None}
    assert {"ticket_created", "claimed", "released", "assigned", "customer_message",
            "agent_reply", "note_added", "status_changed", "priority_changed", "resolved",
            "reopened", "auto_closed", "holiday_added", "holiday_removed"} <= types
    assert TestClient(api.app).get("/api/lead/audit/verify").status_code == 401
    assert T0.tzinfo is UTC


def test_i10_d041_write_after_window_closes_old_ticket_in_same_transaction(api: ApiHarness) -> None:
    """I-10 / D-041: resolved past the 7-day window and the sweep has NOT run yet → the customer's
    message creates the child ticket AND closes the old one in the same request: reason
    reopen_window_expired, actor customer, child_ticket_id in the payload. The sweep then has
    nothing left to do for it."""
    agent = api.agent("Divya")
    old_id, token = _in_state(api, agent, S.resolved)
    old = api.ticket(old_id)
    assert old.resolved_at is not None
    api.clock.now = old.resolved_at + timedelta(days=7)  # exactly at the boundary (D-025)
    out = api.customer(token).post("/api/customer/ticket/messages",
                                   json={"body": "Same problem again"}).json()
    child_id = api.ticket_id(out["new_ticket_number"])

    closed = api.ticket(old_id)
    assert (closed.status, closed.close_reason) == (S.closed, CloseReason.reopen_window_expired)
    assert closed.closed_at == api.clock.now
    assert closed.version == old.version + 1
    assert api.ticket(child_id).parent_ticket_id == old_id
    with Session(api.owner) as s:
        rows = s.scalars(select(AuditEvent).where(AuditEvent.ticket_id == old_id)
                         .order_by(AuditEvent.id)).all()
    closing, status = rows[-2], rows[-1]
    assert closing.event_type == "auto_closed"
    assert closing.payload == {"reason": "reopen_window_expired", "child_ticket_id": str(child_id)}
    assert (closing.actor_type.value, closing.actor_id) == ("customer", old.customer_id)
    assert closing.created_at == api.clock.now
    assert (status.event_type, status.payload) == ("status_changed",
                                                    {"from": "resolved", "to": "closed"})
    view = api.customer(token).get("/api/customer/ticket").json()
    assert view["status"] == "closed" and view["message_starts_new_ticket"] is True
    api.sweep()
    assert api.ticket(old_id).version == closed.version  # the sweep did not touch it again
    assert agent.client.get(f"/api/agent/tickets/{old_id}").json()["ticket"]["status"] == "closed"
