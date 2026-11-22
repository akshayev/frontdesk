"""Domain layer on real PostgreSQL (app/domain/tickets.py, app/jobs/sweep.py): the §4 state
machine, SLA clock wiring, version bumps and audit events, driven with injected DB times."""

import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.audit.chain import verify
from app.db import RequestContext, load_holidays
from app.domain import tickets as d
from app.jobs.sweep import run_sweep
from app.models import AgentRole, AuditEvent, CloseReason, Ticket, TicketStatus
from app.sla.calendar import add_working_minutes
from app.sla.policy import Priority
from tests.integration.conftest import migrated_database

# Mon 23 Nov 2026 10:00 IST
T0 = datetime(2026, 11, 23, 4, 30, tzinfo=UTC)
TxFactory = Callable[[datetime], AbstractContextManager[RequestContext]]


@pytest.fixture(scope="module")
def engines() -> Iterator[tuple[Engine, Engine]]:
    with migrated_database("frontdesk_domain_test") as pair:
        yield pair


@pytest.fixture
def tx(engines: tuple[Engine, Engine]) -> TxFactory:
    @contextmanager
    def _tx(now: datetime) -> Iterator[RequestContext]:
        with Session(engines[1], expire_on_commit=False) as s, s.begin():
            yield RequestContext(now=now, session=s)
    return _tx


def _agent(engines: tuple[Engine, Engine], name: str, role: AgentRole = AgentRole.agent):
    from app.models import Agent
    with Session(engines[0], expire_on_commit=False) as s, s.begin():
        agent = Agent(email=f"{name.lower()}-{uuid.uuid4().hex[:8]}@example.com", name=name,
                      role=role, password_hash="x", created_at=T0)
        s.add(agent)
    return agent


def _new(tx: TxFactory, now: datetime = T0, priority: Priority = Priority.medium) -> Ticket:
    with tx(now) as ctx:
        ticket, token = d.create_ticket(
            ctx, load_holidays(ctx.session), channel="public", customer_name="Asha",
            customer_email="Asha@Example.com", subject="Printer", body="It is broken",
            priority=priority)
        assert len(token) >= 40
    return ticket


def _events(engines: tuple[Engine, Engine], ticket_id: uuid.UUID) -> list[tuple[str, dict]]:
    with Session(engines[0]) as s:
        rows = s.scalars(select(AuditEvent).where(AuditEvent.ticket_id == ticket_id)
                         .order_by(AuditEvent.id)).all()
        return [(r.event_type, r.payload) for r in rows]


def _get(tx: TxFactory, ticket_id: uuid.UUID) -> Ticket:
    with tx(T0) as ctx:
        ticket = ctx.session.get(Ticket, ticket_id)
        assert ticket is not None
        return ticket


def test_full_lifecycle_versions_and_events(tx: TxFactory, engines) -> None:
    agent = _agent(engines, "Priya")
    t = _new(tx)
    assert (t.status, t.version) == (TicketStatus.new, 0)
    with tx(T0 + timedelta(minutes=5)) as ctx:
        t = d.claim(ctx, t.id, agent)
    assert (t.status, t.assignee_id, t.version) == (TicketStatus.open, agent.id, 1)
    t1 = T0 + timedelta(minutes=30)
    with tx(t1) as ctx:
        t = d.agent_reply(ctx, frozenset(), t.id, agent, "Which model?", 1, True)
    assert (t.status, t.first_response_at, t.paused_at, t.version) == (
        TicketStatus.waiting_on_customer, t1, t1, 2)
    t2 = T0 + timedelta(hours=2)
    with tx(t2) as ctx:
        result = d.customer_message(ctx, frozenset(), t.id, "HP 1020")
    t = result.ticket
    assert result.new_ticket_token is None
    assert (t.status, t.paused_at, t.version) == (TicketStatus.open, None, 3)
    # D-026: due moved forward by the 90 working minutes spent waiting
    assert t.resolution_due_at == add_working_minutes(T0, 1620 + 90, frozenset())
    with tx(T0 + timedelta(hours=3)) as ctx:
        t = d.resolve(ctx, frozenset(), t.id, agent, 3)
    assert (t.status, t.version) == (TicketStatus.resolved, 4)
    with tx(T0 + timedelta(days=1)) as ctx:
        t = d.customer_reopen(ctx, frozenset(), t.id)
    assert (t.status, t.reopen_count, t.version) == (TicketStatus.open, 1, 5)
    assert [e for e, _ in _events(engines, t.id)] == [
        "ticket_created", "customer_message", "claimed", "agent_reply", "status_changed",
        "customer_message", "status_changed", "resolved", "status_changed", "reopened",
        "status_changed"]
    with tx(T0) as ctx:
        assert verify(ctx.session).ok


def test_claim_loser_gets_owner_name(tx: TxFactory, engines) -> None:
    a, b = _agent(engines, "Ravi"), _agent(engines, "Kiran")
    t = _new(tx)
    with tx(T0) as ctx:
        d.claim(ctx, t.id, a)
    with pytest.raises(d.DomainError) as err, tx(T0) as ctx:
        d.claim(ctx, t.id, b)
    assert err.value.code == "already_claimed"
    assert err.value.extra["owner"]["name"] == "Ravi"


def test_guards(tx: TxFactory, engines) -> None:
    a, b = _agent(engines, "Anil"), _agent(engines, "Divya")
    t = _new(tx)
    cases: list[tuple[Callable[[RequestContext], object], str]] = [
        (lambda c: d.agent_reply(c, frozenset(), t.id, a, "x", 0, False), "illegal_transition"),
        (lambda c: d.resolve(c, frozenset(), t.id, a, 0), "illegal_transition"),
        (lambda c: d.add_note(c, t.id, a, "x", 7), "stale_version"),
        (lambda c: d.claim(c, uuid.uuid4(), a), "not_found"),
    ]
    for call, code in cases:
        with pytest.raises(d.DomainError) as err, tx(T0) as ctx:
            call(ctx)
        assert err.value.code == code
    with tx(T0) as ctx:
        d.claim(ctx, t.id, a)
    for call, code in [
        (lambda c: d.agent_reply(c, frozenset(), t.id, b, "x", 1, False), "forbidden"),
        (lambda c: d.resolve(c, frozenset(), t.id, a, 1), "reply_required"),
        (lambda c: d.customer_reopen(c, frozenset(), t.id), "illegal_transition"),
    ]:
        with pytest.raises(d.DomainError) as err, tx(T0) as ctx:
            call(ctx)
        assert err.value.code == code


def test_sweep_closes_and_is_idempotent(tx: TxFactory, engines) -> None:
    agent = _agent(engines, "Meena")
    waiting, resolved = _new(tx), _new(tx)
    with tx(T0) as ctx:
        d.claim(ctx, waiting.id, agent)
        d.claim(ctx, resolved.id, agent)
        d.agent_reply(ctx, frozenset(), waiting.id, agent, "?", 1, True)
        d.agent_reply(ctx, frozenset(), resolved.id, agent, "done", 1, False)
        d.resolve(ctx, frozenset(), resolved.id, agent, 2)
    with tx(T0) as ctx:
        holidays = load_holidays(ctx.session)
    just_before = add_working_minutes(T0, 2699, holidays)
    with tx(just_before) as ctx:
        assert run_sweep(ctx.session, ctx.now, holidays).no_customer_reply == 0
    later = T0 + timedelta(days=8)
    for _ in range(2):
        with tx(later) as ctx:
            run_sweep(ctx.session, ctx.now, holidays)
    w, r = _get(tx, waiting.id), _get(tx, resolved.id)
    assert (w.status, w.close_reason) == (TicketStatus.closed, CloseReason.no_customer_reply)
    assert (r.status, r.close_reason) == (TicketStatus.closed, CloseReason.reopen_window_expired)
    assert [e for e, _ in _events(engines, w.id)][-2:] == ["auto_closed", "status_changed"]
    assert [e for e, _ in _events(engines, w.id)].count("auto_closed") == 1  # idempotent
    with tx(later) as ctx:
        result = d.customer_message(ctx, holidays, r.id, "It broke again")
    child = result.ticket
    assert result.new_ticket_token is not None
    assert (child.parent_ticket_id, child.subject, child.status) == (r.id, "Re: Printer",
                                                                     TicketStatus.new)


def test_customer_reused_by_email(tx: TxFactory, engines) -> None:
    a, b = _new(tx), _new(tx)
    assert a.customer_id == b.customer_id
    with Session(engines[0]) as s:
        assert s.execute(text("SELECT email FROM customers WHERE id = :i"),
                         {"i": a.customer_id}).scalar_one() == "asha@example.com"
