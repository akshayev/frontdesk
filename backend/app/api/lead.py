"""Lead API. Implements: RPT-1, RPT-2, AUD-3, SLA-3 (holidays), CLM-2 (reassign), D-014.

Every endpoint: require_lead (403 for a plain agent), CSRF header on writes (middleware),
rate-limit group `agent` (120/min/session).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.api.agent import ticket_detail
from app.api.csv_export import csv_response, ist
from app.audit.chain import verify
from app.db import Tx, load_holidays
from app.domain import holidays as holiday_domain
from app.domain import tickets as domain
from app.domain.reports import LateRow, late_report
from app.schemas.agent import (
    AgentRef,
    AssignIn,
    HolidayIn,
    HolidayOut,
    LateRowOut,
    MissedTargetOut,
    PriorityChangeOut,
    TicketDetail,
    VerifyOut,
)
from app.security.ratelimit import limit_agent
from app.security.sessions import CurrentLead

router = APIRouter(prefix="/api/lead", tags=["lead"])


@router.post("/tickets/{ticket_id}/assign", response_model=TicketDetail)
@limit_agent
def assign(request: Request, ticket_id: uuid.UUID, body: AssignIn, ctx: Tx,
           lead: CurrentLead) -> TicketDetail:
    """CLM-2: the lead (re)assigns any non-closed ticket."""
    ticket = domain.assign(ctx, ticket_id, lead, body.agent_id, body.expected_version)
    return ticket_detail(ctx, ticket, lead)


def _row_out(row: LateRow) -> LateRowOut:
    return LateRowOut(
        ticket_id=row.ticket_id, number=row.number, subject=row.subject, status=row.status,
        assignee=None if row.assignee_id is None else AgentRef(
            id=row.assignee_id, name=row.assignee_name or "Unknown agent"),
        initial_priority=row.initial_priority, current_priority=row.current_priority,
        priority_history=[PriorityChangeOut(at=c.at, from_priority=c.from_priority,
                                            to_priority=c.to_priority)
                          for c in row.priority_history],
        missed=[MissedTargetOut(target=m.target, working_minutes_late=m.working_minutes_late,
                                due_at=m.due_at, met_at=m.met_at) for m in row.missed],
        waiting_on_customer_working_minutes=row.waiting_on_customer_working_minutes,
    )


@router.get("/reports/late", response_model=list[LateRowOut])
@limit_agent
def late(request: Request, ctx: Tx, lead: CurrentLead) -> list[LateRowOut]:
    """RPT-1 "Late tickets"."""
    return [_row_out(r) for r in late_report(ctx.session, ctx.now, load_holidays(ctx.session))]


@router.get("/reports/late.csv")
@limit_agent
def late_csv(request: Request, ctx: Tx, lead: CurrentLead) -> Response:
    """RPT-2: the same report as CSV (built from tickets + events only; formula-guarded)."""
    rows = late_report(ctx.session, ctx.now, load_holidays(ctx.session))

    def missed_by(row: LateRow, target: str) -> str:
        return next((str(m.working_minutes_late) for m in row.missed if m.target == target), "")

    def history(row: LateRow) -> str:
        return "; ".join(f"{ist(c.at)} {c.from_priority.value}->{c.to_priority.value}"
                         for c in row.priority_history)

    header = ["ticket", "subject", "status", "assignee", "initial_priority", "current_priority",
              "priority_history", "response_late_working_min", "resolution_late_working_min",
              "waiting_on_customer_working_min"]
    return csv_response("late-tickets.csv", header, (
        [f"FD-{r.number}", r.subject, r.status.value, r.assignee_name or "",
         r.initial_priority.value, r.current_priority.value, history(r),
         missed_by(r, "response"), missed_by(r, "resolution"),
         r.waiting_on_customer_working_minutes]
        for r in rows))


@router.get("/holidays", response_model=list[HolidayOut])
@limit_agent
def list_holidays(request: Request, ctx: Tx, lead: CurrentLead) -> list[HolidayOut]:
    """SLA-3 / D-014 holiday list."""
    return [HolidayOut.model_validate(h) for h in holiday_domain.list_holidays(ctx)]


@router.post("/holidays", response_model=HolidayOut, status_code=201)
@limit_agent
def add_holiday(request: Request, body: HolidayIn, ctx: Tx, lead: CurrentLead) -> HolidayOut:
    """Add a holiday (audited holiday_added)."""
    return HolidayOut.model_validate(holiday_domain.add_holiday(ctx, lead, body.date, body.name))


@router.delete("/holidays/{day}", status_code=204)
@limit_agent
def remove_holiday(request: Request, day: date, ctx: Tx, lead: CurrentLead) -> Response:
    """Remove a holiday (audited holiday_removed)."""
    holiday_domain.remove_holiday(ctx, lead, day)
    return Response(status_code=204)


@router.get("/audit/verify", response_model=VerifyOut)
@limit_agent
def audit_verify(request: Request, ctx: Tx, lead: CurrentLead) -> VerifyOut:
    """AUD-3: recompute the whole hash chain."""
    result = verify(ctx.session)
    return VerifyOut(ok=result.ok, checked=result.checked, first_bad_id=result.first_bad_id)
