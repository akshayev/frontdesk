"""The three incidents through the real HTTP API on PostgreSQL (TEST-PLAN I-1, I-2, I-3, I-4,
I-14): INC-0291 double claim, INC-0304 note leak, customer token scope."""

import json
import threading
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models import AgentRole
from tests.integration.api_support import AgentHandle, ApiHarness


def _race_claim(agents: list[AgentHandle], ticket_id: uuid.UUID) -> dict[str, tuple[int, dict]]:
    """Each agent claims from its own thread; a barrier releases them at the same moment."""
    barrier = threading.Barrier(len(agents))
    results: dict[str, tuple[int, dict]] = {}

    def grab(agent: AgentHandle) -> None:
        barrier.wait()
        resp = agent.client.post(f"/api/agent/tickets/{ticket_id}/claim")
        results[agent.name] = (resp.status_code, resp.json())

    threads = [threading.Thread(target=grab, args=(a,)) for a in agents]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_i1_concurrent_claim_exactly_one_wins(api: ApiHarness) -> None:
    """CLM-1: two agents, two threads, separate clients and DB sessions, released together
    by a barrier → exactly one 200 and one 409 already_claimed naming the winner (5 rounds)."""
    priya, arjun = api.agent("Priya"), api.agent("Arjun")
    for _ in range(5):
        tid, _ = api.public_ticket()
        results = _race_claim([priya, arjun], tid)
        codes = sorted(code for code, _ in results.values())
        assert codes == [200, 409], results
        winner = next(n for n, (c, _) in results.items() if c == 200)
        loser_body = next(b for c, b in results.values() if c == 409)
        assert loser_body["error"] == "already_claimed"
        assert loser_body["owner"]["name"] == winner
        assert winner in loser_body["message"]
        assert api.ticket(tid).version == 1  # claimed once


def test_i2_non_assignee_reply_is_403(api: ApiHarness) -> None:
    """CLM-2: only the assignee may reply (the lead too must reassign first)."""
    owner, other = api.agent("Kavya"), api.agent("Rahul")
    lead = api.agent("Meera", AgentRole.lead)
    tid, _ = api.public_ticket()
    owner.client.post(f"/api/agent/tickets/{tid}/claim")
    v = api.version(owner, tid)
    for intruder in (other, lead):
        resp = intruder.client.post(f"/api/agent/tickets/{tid}/replies",
                                    json={"body": "hi", "expected_version": v})
        assert resp.status_code == 403 and resp.json()["error"] == "forbidden"
        resp = intruder.client.post(f"/api/agent/tickets/{tid}/resolve",
                                    json={"expected_version": v})
        assert resp.status_code == 403
    assert api.version(owner, tid) == v  # nothing changed


def test_i3_stale_version_after_customer_message_and_after_colleague_note(
        api: ApiHarness) -> None:
    """CLM-3: the reply the agent typed against version v is refused (409 stale_version) once
    the customer wrote, and again once a colleague added a note."""
    owner, colleague = api.agent("Ananya"), api.agent("Vikram")
    tid, token = api.public_ticket()
    owner.client.post(f"/api/agent/tickets/{tid}/claim")
    v = api.version(owner, tid)

    api.customer(token).post("/api/customer/ticket/messages", json={"body": "Any update?"})
    resp = owner.client.post(f"/api/agent/tickets/{tid}/replies",
                             json={"body": "Restart it", "expected_version": v})
    assert resp.status_code == 409
    assert resp.json()["error"] == "stale_version"
    assert resp.json()["current_version"] == v + 1

    v = api.version(owner, tid)
    resp = colleague.client.post(f"/api/agent/tickets/{tid}/notes",
                                 json={"body": "Don't suggest a restart", "expected_version": v})
    assert resp.status_code == 200
    resp = owner.client.post(f"/api/agent/tickets/{tid}/replies",
                             json={"body": "Restart it", "expected_version": v})
    assert resp.status_code == 409 and resp.json()["error"] == "stale_version"
    v = api.version(owner, tid)
    resp = owner.client.post(f"/api/agent/tickets/{tid}/replies",
                             json={"body": "We are checking the logs", "expected_version": v})
    assert resp.status_code == 200


def test_i4_canary_note_never_leaves_the_agent_detail(api: ApiHarness) -> None:
    """LEAK-1..3 (INC-0304): a note body "CANARY-<uuid>" is stored, then EVERY customer and
    public endpoint, every POST response, the transcript CSV, the late report (JSON + CSV), all
    agent list views and every audit payload are searched for it. Only the agent ticket
    detail may contain it — asserted, to prove the canary really was stored."""
    canary = f"CANARY-{uuid.uuid4()}"
    agent = api.agent("Sneha")
    lead = api.agent("Meera", AgentRole.lead)
    tid, token = api.public_ticket(priority="urgent")
    cust = api.customer(token)
    seen: list[str] = []

    def record(resp, agent_detail: bool = False) -> dict:  # type: ignore[no-untyped-def]
        """Keep the response for the canary search — except agent mutations, which return the
        agent ticket-detail view (the one place notes belong)."""
        assert resp.status_code < 300, resp.text
        if not agent_detail:
            seen.append(resp.text)
        return resp.json() if "json" in resp.headers.get("content-type", "") else {}

    record(agent.client.post(f"/api/agent/tickets/{tid}/claim"), agent_detail=True)
    api.clock.advance(hours=3)  # urgent response (120 working min) is now late → late report
    v = api.version(agent, tid)
    detail = record(agent.client.post(f"/api/agent/tickets/{tid}/replies",
                                      json={"body": "Looking into it", "expected_version": v}),
                    agent_detail=True)
    # the canary note is the LATEST activity, so a preview built from it would show it
    detail = record(agent.client.post(f"/api/agent/tickets/{tid}/notes", json={
        "body": f"{canary} customer is on the old plan", "expected_version": detail["version"]}),
        agent_detail=True)
    assert any(canary in n["body"] for n in detail["notes"])  # stored, visible to agents

    # every customer and public endpoint
    record(cust.get("/api/customer/ticket"))
    record(cust.post("/api/customer/ticket/messages", json={"body": "Thanks"}))
    v = api.version(agent, tid)
    record(agent.client.post(f"/api/agent/tickets/{tid}/resolve", json={"expected_version": v}),
           agent_detail=True)
    record(cust.get("/api/customer/ticket"))
    record(cust.post("/api/customer/ticket/reopen"))
    record(cust.get("/api/customer/ticket"))
    record(TestClient(api.app).post("/api/public/tickets", json={
        "name": "B", "email": "b@example.com", "subject": "s", "description": "d",
        "priority": "low"}))
    # exports, report, lists
    record(agent.client.get(f"/api/agent/tickets/{tid}/transcript.csv"))
    late = record(lead.client.get("/api/lead/reports/late"))
    assert any(r["ticket_id"] == str(tid) for r in late)  # the ticket IS in the report
    record(lead.client.get("/api/lead/reports/late.csv"))
    for view in ("mine", "unassigned", "all", "late", "waiting"):
        rows = record(agent.client.get(f"/api/agent/tickets?view={view}"))
        if view == "all":
            assert any(r["id"] == str(tid) for r in rows)
    # every audit payload
    with api.owner.connect() as conn:
        payloads = conn.execute(text("SELECT payload::text FROM audit_events")).scalars().all()
    seen.extend(payloads)

    leaks = [s[:200] for s in seen if canary in s]
    assert leaks == []
    final = agent.client.get(f"/api/agent/tickets/{tid}")
    assert canary in final.text  # the only place it may appear
    assert canary not in json.dumps(final.json()["messages"])
    assert canary not in json.dumps(final.json()["events"])


def test_i14_token_scopes_exactly_one_ticket(api: ApiHarness) -> None:
    """SECURITY §3: token A only ever opens ticket A; a wrong, altered or missing token, or an
    agent session, gets 404 (indistinguishable from a missing ticket)."""
    _, token_a = api.public_ticket(subject="Ticket A")
    _, token_b = api.public_ticket(subject="Ticket B")
    assert api.customer(token_a).get("/api/customer/ticket").json()["subject"] == "Ticket A"
    assert api.customer(token_b).get("/api/customer/ticket").json()["subject"] == "Ticket B"
    altered = token_a[:-1] + ("A" if token_a[-1] != "A" else "B")
    agent = api.agent("Karthik")
    for client in (api.customer(altered), api.customer("x" * 500), TestClient(api.app),
                   agent.client):
        for method, path in (("get", "/api/customer/ticket"),
                             ("post", "/api/customer/ticket/reopen")):
            resp = getattr(client, method)(path)
            assert resp.status_code == 404 and resp.json()["error"] == "not_found"
        resp = client.post("/api/customer/ticket/messages", json={"body": "hi"})
        assert resp.status_code == 404
    # the customer response carries no internal ids
    body = api.customer(token_a).get("/api/customer/ticket").json()
    assert not {"id", "customer_id", "assignee_id", "version"} & set(body)
