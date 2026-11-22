"""Lead-editable holidays. Implements: SLA-3, D-014, AUD-1 (holiday_added / holiday_removed).

Due times already stored on tickets are not recalculated when a holiday is added or removed;
the new calendar applies to SLA maths from that request on.
"""

from datetime import date

from sqlalchemy import select

from app.audit.chain import append_event
from app.db import RequestContext
from app.domain.tickets import DomainError, validation
from app.models import ActorType, Agent, Holiday


def list_holidays(ctx: RequestContext) -> list[Holiday]:
    """All holidays, oldest first."""
    return list(ctx.session.scalars(select(Holiday).order_by(Holiday.date)))


def add_holiday(ctx: RequestContext, lead: Agent, day: date, name: str) -> Holiday:
    """SLA-3: add a non-working date; audited holiday_added {date, name}."""
    if ctx.session.get(Holiday, day) is not None:
        raise validation(f"{day.isoformat()} is already a holiday.")
    holiday = Holiday(date=day, name=name, created_by=lead.id)
    ctx.session.add(holiday)
    ctx.session.flush()
    append_event(ctx.session, ctx.now, None, ActorType.agent, lead.id, "holiday_added",
                 {"date": day.isoformat(), "name": name})
    return holiday


def remove_holiday(ctx: RequestContext, lead: Agent, day: date) -> None:
    """SLA-3: remove a holiday; audited holiday_removed {date, name}."""
    holiday = ctx.session.get(Holiday, day, with_for_update=True)
    if holiday is None:
        raise DomainError("not_found", 404, "Holiday not found.")
    name = holiday.name
    ctx.session.delete(holiday)
    ctx.session.flush()
    append_event(ctx.session, ctx.now, None, ActorType.agent, lead.id, "holiday_removed",
                 {"date": day.isoformat(), "name": name})
