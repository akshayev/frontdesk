"""scripts/seed.py on a throwaway database: valid audit chain, every status present, refusal
rules (S3 seed brief)."""

import secrets
from collections.abc import Iterator

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import load_holidays
from app.domain.tickets import clock_of
from app.models import Agent, AgentRole, AuditEvent, InternalNote, Ticket, TicketStatus
from app.sla import policy
from scripts import seed
from tests.integration.conftest import migrated_database


@pytest.fixture(scope="module")
def seeded_db() -> Iterator[tuple[Engine, Engine, seed.SeedReport, Settings]]:
    settings = get_settings().model_copy(update={
        "seed_demo_password": SecretStr(secrets.token_urlsafe(16)), "app_env": "development"})
    with migrated_database("frontdesk_seed_test") as (owner, app):
        yield owner, app, seed.run(settings, engine=app), settings


def test_seed_chain_valid_and_every_status_present(seeded_db) -> None:
    _, _, report, _ = seeded_db
    assert report.verify_ok and report.verify_checked > 80
    assert set(report.status_counts) == {s.value for s in TicketStatus}
    assert sum(report.status_counts.values()) == 20
    assert len(report.links) == 20 and all("/t#" in link for link in report.links.values())


def test_seed_covers_the_demo_scenarios(seeded_db) -> None:
    owner, _, _, _ = seeded_db
    with Session(owner) as s:
        tickets = list(s.scalars(select(Ticket)))
        now = s.scalar(select(func.now()))
        holidays = load_holidays(s)
        events = {e for (e,) in s.execute(select(AuditEvent.event_type).distinct())}
        notes = s.scalar(select(func.count(func.distinct(InternalNote.ticket_id))))
    statuses = [policy.target_statuses(clock_of(t), now, holidays) for t in tickets]
    states = {(r.target, r.state) for pair in statuses for r in pair}
    assert {("response", "late"), ("resolution", "late"), ("response", "at_risk")} <= states
    assert {t.close_reason.value for t in tickets if t.close_reason} == {
        "no_customer_reply", "reopen_window_expired"}
    assert any(t.parent_ticket_id for t in tickets)
    assert any(t.reopen_count == 1 for t in tickets)
    assert {"priority_changed", "released", "assigned", "auto_closed", "reopened"} <= events
    assert notes >= 4


def test_seed_creates_two_leads(seeded_db) -> None:
    """D-044: two lead accounts, so one locked-out lead cannot block an evaluation."""
    owner, _, _, _ = seeded_db
    with Session(owner) as s:
        roles = {email: role for email, role in s.execute(select(Agent.email, Agent.role))}
    leads = sorted(email for email, role in roles.items() if role == AgentRole.lead)
    assert leads == ["meera@arvo.example", "rohini@arvo.example"]
    assert len(roles) == 11 and all(email.endswith("@arvo.example") for email in roles)


def test_seed_refuses_non_empty_db_and_missing_password(seeded_db) -> None:
    _, app, _, settings = seeded_db
    with pytest.raises(seed.SeedRefused, match="not empty"):
        seed.run(settings, engine=app)
    with pytest.raises(seed.SeedRefused, match="SEED_DEMO_PASSWORD"):
        seed.run(settings.model_copy(update={"seed_demo_password": None}), engine=app)
