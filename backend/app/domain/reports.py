"""Lead "Late tickets" report. Implements: RPT-1, RPT-2, SLA-7, WAIT-1 (D-025).

Built only from ticket rows and audit events (priority_changed, status_changed, ticket_created)
— never from messages or notes, so the report and its CSV cannot contain note bodies (RPT-2).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.tickets import clock_of
from app.models import Agent, AuditEvent, Ticket, TicketStatus
from app.sla import policy
from app.sla.calendar import Holidays, working_minutes_between
from app.sla.policy import Priority

WAITING = TicketStatus.waiting_on_customer.value


@dataclass(frozen=True)
class PriorityChange:
    """One priority_changed event (PRI-5)."""

    at: datetime
    from_priority: Priority
    to_priority: Priority


@dataclass(frozen=True)
class MissedTarget:
    """A target that is late (SLA-7) and by how many working minutes (policy.target_statuses)."""

    target: policy.TargetName
    working_minutes_late: int
    due_at: datetime
    met_at: datetime | None


@dataclass(frozen=True)
class LateRow:
    """RPT-1: ticket, assignee, priority history, missed targets, time waiting on customer."""

    ticket_id: uuid.UUID
    number: int
    subject: str
    status: TicketStatus
    assignee_id: uuid.UUID | None
    assignee_name: str | None
    initial_priority: Priority
    current_priority: Priority
    priority_history: list[PriorityChange]
    missed: list[MissedTarget]
    waiting_on_customer_working_minutes: int


def waiting_minutes(status_events: list[tuple[datetime, dict[str, Any]]], now: datetime,
                    holidays: Holidays) -> int:
    """WAIT-1: total working minutes spent in waiting_on_customer, from status_changed events
    in order (an interval still open at `now` counts up to now)."""
    total = 0
    started: datetime | None = None
    for at, payload in status_events:
        if payload.get("to") == WAITING and started is None:
            started = at
        elif payload.get("from") == WAITING and started is not None:
            total += working_minutes_between(started, at, holidays)
            started = None
    if started is not None:
        total += working_minutes_between(started, now, holidays)
    return total


def late_report(session: Session, now: datetime, holidays: Holidays) -> list[LateRow]:
    """RPT-1: every ticket (any status) with at least one late target, newest first.

    A late target always has its due time in the past (met late, overdue now, or overdue at
    the pause), so only tickets with a past due time are examined.
    """
    tickets = list(session.scalars(
        select(Ticket)
        .where(or_(Ticket.first_response_due_at < now, Ticket.resolution_due_at < now))
        .order_by(Ticket.number.desc())
    ))
    late: list[tuple[Ticket, list[MissedTarget]]] = []
    for ticket in tickets:
        missed = [
            MissedTarget(s.target, s.minutes, s.due_at, s.met_at)
            for s in policy.target_statuses(clock_of(ticket), now, holidays)
            if s.state == "late"
        ]
        if missed:
            late.append((ticket, missed))
    if not late:
        return []

    ids = [t.id for t, _ in late]
    events: dict[uuid.UUID, list[AuditEvent]] = {i: [] for i in ids}
    for event in session.scalars(
        select(AuditEvent)
        .where(AuditEvent.ticket_id.in_(ids),
               AuditEvent.event_type.in_(["ticket_created", "priority_changed",
                                          "status_changed"]))
        .order_by(AuditEvent.id)
    ):
        assert event.ticket_id is not None
        events[event.ticket_id].append(event)
    assignee_ids = {t.assignee_id for t, _ in late if t.assignee_id is not None}
    names = dict(session.execute(
        select(Agent.id, Agent.name).where(Agent.id.in_(assignee_ids))
    ).all()) if assignee_ids else {}

    rows = []
    for ticket, missed in late:
        evs = events[ticket.id]
        history = [
            PriorityChange(e.created_at, Priority(e.payload["from"]), Priority(e.payload["to"]))
            for e in evs if e.event_type == "priority_changed"
        ]
        initial = history[0].from_priority if history else ticket.priority
        status_events = [(e.created_at, e.payload) for e in evs
                         if e.event_type == "status_changed"]
        rows.append(LateRow(
            ticket_id=ticket.id,
            number=ticket.number,
            subject=ticket.subject,
            status=ticket.status,
            assignee_id=ticket.assignee_id,
            assignee_name=names.get(ticket.assignee_id) if ticket.assignee_id else None,
            initial_priority=initial,
            current_priority=ticket.priority,
            priority_history=history,
            missed=missed,
            waiting_on_customer_working_minutes=waiting_minutes(status_events, now, holidays),
        ))
    return rows
