"""Background auto-close sweep. Implements: WAIT-4, RO-3 (ARCHITECTURE §9; D-010, D-011, D-025).

`run_sweep` is idempotent: a closed ticket is never selected again, and a ticket that does not
qualify yet is left untouched. Rows are locked FOR UPDATE SKIP LOCKED, so the sweep never
waits on (or deadlocks with) an agent or customer request holding the same ticket — a skipped
ticket is simply handled by the next run. SLA badges never depend on the sweep (computed at
read time).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import RequestContext
from app.domain.tickets import auto_close
from app.models import CloseReason, Ticket, TicketStatus
from app.sla import policy
from app.sla.calendar import Holidays


@dataclass(frozen=True)
class SweepResult:
    """How many tickets one run closed, per reason."""

    no_customer_reply: int
    reopen_window_expired: int


def _locked(session: Session, status: TicketStatus) -> list[Ticket]:
    return list(session.scalars(
        select(Ticket)
        .where(Ticket.status == status)
        .order_by(Ticket.number)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ))


def run_sweep(session: Session, now: datetime, holidays: Holidays) -> SweepResult:
    """WAIT-4: waiting tickets silent for >= 2700 working minutes → closed/no_customer_reply.
    RO-3: resolved tickets past the 7-day reopen window → closed/reopen_window_expired.
    Actor system; events auto_closed {reason} + status_changed; version += 1. `now` is the
    caller's DB time (ARCHITECTURE §6)."""
    ctx = RequestContext(now=now, session=session)
    silent = 0
    for ticket in _locked(session, TicketStatus.waiting_on_customer):
        if ticket.paused_at is not None and policy.should_auto_close(ticket.paused_at, now,
                                                                     holidays):
            auto_close(ctx, ticket, CloseReason.no_customer_reply)
            silent += 1
    expired = 0
    for ticket in _locked(session, TicketStatus.resolved):
        if ticket.resolved_at is not None and not policy.can_reopen(ticket.resolved_at, now):
            auto_close(ctx, ticket, CloseReason.reopen_window_expired)
            expired += 1
    return SweepResult(no_customer_reply=silent, reopen_window_expired=expired)
