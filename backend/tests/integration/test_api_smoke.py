"""Smoke test of every agent / lead / customer / public endpoint (ARCHITECTURE §10)."""

from datetime import date

from app.models import AgentRole
from tests.integration.api_support import ApiHarness


def test_every_endpoint_happy_path(api: ApiHarness) -> None:
    priya = api.agent("Priya Sharma")
    meera = api.agent("Meera Iyer", AgentRole.lead)
    tid, token = api.public_ticket(subject="=cmd|' /C calc'!A0", priority="urgent")
    cust = api.customer(token)

    rows = priya.client.get("/api/agent/tickets?view=unassigned").json()
    row = next(r for r in rows if r["id"] == str(tid))
    assert row["badge"] == {"state": "on_track", "target": "response", "minutes": 120}
    assert row["preview"] == "I cannot log in."
    assert priya.client.post(f"/api/agent/tickets/{tid}/claim").status_code == 200
    v = api.version(priya, tid)
    detail = priya.client.post(f"/api/agent/tickets/{tid}/notes",
                               json={"body": "check SSO", "expected_version": v}).json()
    assert [n["body"] for n in detail["notes"]] == ["check SSO"]
    api.clock.advance(minutes=10)
    detail = priya.client.post(f"/api/agent/tickets/{tid}/replies", json={
        "body": "Which browser?", "expected_version": detail["version"],
        "wait_for_customer": True}).json()
    assert detail["ticket"]["status"] == "waiting_on_customer"
    assert priya.client.get("/api/agent/tickets?view=waiting").json()[0]["id"] == str(tid)

    view = cust.get("/api/customer/ticket").json()
    assert [m["author"] for m in view["messages"]] == ["You", "Support"]
    assert view["messages"][1]["agent_first_name"] == "Priya"
    api.clock.advance(minutes=20)
    assert cust.post("/api/customer/ticket/messages", json={"body": "Chrome"}).json() == {
        "new_ticket_number": None, "new_ticket_link": None}
    v = api.version(priya, tid)
    resp = priya.client.patch(f"/api/agent/tickets/{tid}/priority",
                              json={"priority": "medium", "expected_version": v})
    assert resp.status_code == 200, resp.text
    v = resp.json()["version"]
    resp = priya.client.post(f"/api/agent/tickets/{tid}/release", json={"expected_version": v})
    assert resp.json()["ticket"]["assignee"] is None
    resp = meera.client.post(f"/api/lead/tickets/{tid}/assign",
                             json={"agent_id": str(priya.id),
                                   "expected_version": resp.json()["version"]})
    assert resp.json()["ticket"]["assignee"]["name"] == "Priya Sharma"
    resp = priya.client.post(f"/api/agent/tickets/{tid}/resolve",
                             json={"expected_version": resp.json()["version"]})
    assert resp.json()["ticket"]["status"] == "resolved"
    assert cust.post("/api/customer/ticket/reopen").json()["status"] == "open"

    csv = priya.client.get(f"/api/agent/tickets/{tid}/transcript.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    assert "Support: Priya Sharma" in csv.text

    created = priya.client.post("/api/agent/tickets", json={
        "customer_name": "Ravi", "customer_email": "ravi@example.com", "subject": "VPN",
        "body": "VPN down", "priority": "low"})
    assert created.status_code == 201 and "/t#" in created.json()["customer_link"]

    assert meera.client.get("/api/lead/reports/late").status_code == 200
    late_csv = meera.client.get("/api/lead/reports/late.csv")
    assert late_csv.status_code == 200 and late_csv.text.startswith("ticket,")
    assert meera.client.post("/api/lead/holidays",
                             json={"date": "2026-12-31", "name": "Year end"}).status_code == 201
    assert {"date": "2026-12-31", "name": "Year end"} in meera.client.get(
        "/api/lead/holidays").json()
    assert meera.client.delete(f"/api/lead/holidays/{date(2026, 12, 31)}").status_code == 204
    assert meera.client.get("/api/lead/audit/verify").json()["ok"] is True
    assert priya.client.get("/api/lead/reports/late").status_code == 403
    assert api.app.openapi_url == "/openapi.json"


def test_d040_lead_agent_list_has_no_emails(api: ApiHarness) -> None:
    """D-040: lead-only; exactly {id, name, role} per agent — no emails (minimum data)."""
    lead = api.agent("Meera Iyer", AgentRole.lead)
    agent = api.agent("Arjun Nair")
    resp = lead.client.get("/api/lead/agents")
    assert resp.status_code == 200
    rows = resp.json()
    assert all(set(r) == {"id", "name", "role"} for r in rows)
    assert {"name": "Arjun Nair", "role": "agent", "id": str(agent.id)} in rows
    assert "@" not in resp.text
    assert agent.client.get("/api/lead/agents").status_code == 403
