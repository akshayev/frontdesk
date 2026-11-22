"""ARCHITECTURE §9: the lifespan starts the sweep (once at startup, real DB now) unless
SWEEP_ENABLED=false; errors are logged and the loop survives."""

import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.jobs.sweep import sweep_once
from app.main import create_app
from app.models import TicketStatus
from tests.integration.api_support import ApiHarness


def _wait_for(predicate, timeout_s: float = 10.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_lifespan_runs_sweep_at_startup(api: ApiHarness) -> None:
    agent = api.agent("Priya")
    api.clock.now = datetime(2026, 10, 1, 5, 0, tzinfo=UTC)  # weeks before the real now
    tid, _ = api.public_ticket()
    agent.client.post(f"/api/agent/tickets/{tid}/claim")
    agent.client.post(f"/api/agent/tickets/{tid}/replies", json={
        "body": "?", "expected_version": 1, "wait_for_customer": True})
    assert api.ticket(tid).status is TicketStatus.waiting_on_customer

    disabled = create_app(settings=get_settings().model_copy(update={"sweep_enabled": False}),
                          engine=api.engine)
    with TestClient(disabled):
        time.sleep(0.3)
    assert api.ticket(tid).status is TicketStatus.waiting_on_customer

    enabled = create_app(settings=get_settings().model_copy(update={"sweep_enabled": True}),
                         engine=api.engine)
    with TestClient(enabled):
        assert _wait_for(lambda: api.ticket(tid).status is TicketStatus.closed)


def test_sweep_once_logs_and_continues_on_error(caplog: pytest.LogCaptureFixture) -> None:
    def broken_factory():  # type: ignore[no-untyped-def]
        raise RuntimeError("database unavailable")

    assert sweep_once(broken_factory) is None  # type: ignore[arg-type]
    assert "sweep failed" in caplog.text
