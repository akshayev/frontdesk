"""Public intake API. Implements: IN-1, LEAK-1, LEAK-2, D-032.

Must not import the notes model or touch the notes table (test A-1). No auth (anyone can report
a problem); rate-limit group `public` (30/min/IP, separate from `customer`, D-032).
"""

from fastapi import APIRouter, Request

from app.db import Tx, load_holidays
from app.domain import tickets as domain
from app.schemas.customer import PublicTicketCreated, PublicTicketIn
from app.security.customer_token import customer_link
from app.security.ratelimit import limit_public

router = APIRouter(prefix="/api/public", tags=["public"])


@router.post("/tickets", response_model=PublicTicketCreated, status_code=201)
@limit_public
def submit(request: Request, body: PublicTicketIn, ctx: Tx) -> PublicTicketCreated:
    """IN-1 "Submit a problem": returns the ticket number and the secret link, once."""
    ticket, token = domain.create_ticket(
        ctx, load_holidays(ctx.session), channel="public", customer_name=body.name,
        customer_email=str(body.email), subject=body.subject, body=body.description,
        priority=body.priority)
    return PublicTicketCreated(number=ticket.number, customer_link=customer_link(
        request.app.state.settings.public_base_url, token))
