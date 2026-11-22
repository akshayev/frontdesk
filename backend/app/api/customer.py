"""Customer API (X-Ticket-Token). Implements: LEAK-1, LEAK-2, AUD-4, WAIT-3, RO-1, RO-2, RO-4.

Must not import the notes model or touch the notes table (test A-1). Responses use
app/schemas/customer.py only: public messages, no agent ids, no SLA dues, no audit events.
Rate-limit group `customer` (30/min/IP, D-032). No CSRF header: the token travels in a custom
header, never in a cookie, so a cross-site page cannot send it.
"""

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.db import RequestContext, Tx, load_holidays
from app.domain import tickets as domain
from app.models import Agent, AuthorType, Message, Ticket, TicketStatus
from app.schemas.customer import (
    CustomerMessageIn,
    CustomerMessageOut,
    CustomerTicketOut,
    CustomerWriteOut,
)
from app.security.customer_token import CustomerTicket, customer_link
from app.security.ratelimit import limit_customer
from app.sla.policy import REOPEN_WINDOW, can_reopen

router = APIRouter(prefix="/api/customer", tags=["customer"])


def _first_name(name: str) -> str:
    return name.split()[0] if name.split() else "Support"


def customer_view(ctx: RequestContext, ticket: Ticket) -> CustomerTicketOut:
    """The customer's ticket page: public messages only (LEAK-1)."""
    rows = ctx.session.execute(
        select(Message.author_type, Message.body, Message.created_at, Agent.name)
        .outerjoin(Agent, Agent.id == Message.author_agent_id)
        .where(Message.ticket_id == ticket.id)
        .order_by(Message.created_at, Message.id)
    ).all()
    reopenable = (ticket.status is TicketStatus.resolved and ticket.resolved_at is not None
                  and can_reopen(ticket.resolved_at, ctx.now))
    return CustomerTicketOut(
        number=ticket.number,
        subject=ticket.subject,
        status=ticket.status,
        priority=ticket.priority,
        created_at=ticket.created_at,
        can_reopen=reopenable,
        message_starts_new_ticket=ticket.status in (TicketStatus.resolved, TicketStatus.closed)
        and not reopenable,
        reopen_until=ticket.resolved_at + REOPEN_WINDOW if reopenable and ticket.resolved_at
        else None,
        messages=[
            CustomerMessageOut(
                author="You" if author is AuthorType.customer else "Support",
                agent_first_name=None if author is AuthorType.customer or agent_name is None
                else _first_name(agent_name),
                body=body,
                created_at=created_at,
            )
            for author, body, created_at, agent_name in rows
        ],
    )


@router.get("/ticket", response_model=CustomerTicketOut)
@limit_customer
def get_ticket(request: Request, ctx: Tx, ticket: CustomerTicket) -> CustomerTicketOut:
    """The one ticket this token opens (I-14: any other token → 404)."""
    return customer_view(ctx, ticket)


@router.post("/ticket/messages", response_model=CustomerWriteOut, status_code=201)
@limit_customer
def post_message(request: Request, body: CustomerMessageIn, ctx: Tx,
                 ticket: CustomerTicket) -> CustomerWriteOut:
    """WAIT-3 resume / RO-2 reopen / RO-4 new ticket (its link returned once)."""
    result = domain.customer_message(ctx, load_holidays(ctx.session), ticket.id, body.body)
    if result.new_ticket_token is None:
        return CustomerWriteOut()
    return CustomerWriteOut(new_ticket_number=result.ticket.number,
                            new_ticket_link=customer_link(
                                request.app.state.settings.public_base_url,
                                result.new_ticket_token))


@router.post("/ticket/reopen", response_model=CustomerTicketOut)
@limit_customer
def reopen(request: Request, ctx: Tx, ticket: CustomerTicket) -> CustomerTicketOut:
    """RO-1: reopen within 7 calendar days of resolution."""
    reopened = domain.customer_reopen(ctx, load_holidays(ctx.session), ticket.id)
    return customer_view(ctx, reopened)
