"""Models for customer and public APIs. Implements: LEAK-1, LEAK-2, IN-1, AUD-4, RO-1, RO-4.

Strictly separate from app/schemas/agent.py (D-022, test A-1): nothing here references the
notes model, the notes table, assignee internals, SLA due times or audit events. Messages show
the author as "You" or "Support" plus the agent's first name — no agent ids or emails.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import BODY_MAX, SUBJECT_MAX, TicketStatus
from app.sla.policy import Priority

Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=BODY_MAX)]


class PublicTicketIn(BaseModel):
    """IN-1 "Submit a problem" form."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    email: EmailStr = Field(max_length=254)
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                              max_length=SUBJECT_MAX)]
    description: Body
    priority: Priority


class PublicTicketCreated(BaseModel):
    """IN-1: the secret link, shown once."""

    number: int
    customer_link: str


class CustomerMessageIn(BaseModel):
    """A customer reply on their ticket."""

    model_config = ConfigDict(extra="forbid")

    body: Body


class CustomerMessageOut(BaseModel):
    """A public message as the customer sees it (AUD-4: exact time)."""

    author: Literal["You", "Support"]
    agent_first_name: str | None
    body: str
    created_at: datetime


class CustomerTicketOut(BaseModel):
    """The customer's one ticket: public conversation and what they can do next."""

    number: int
    subject: str
    status: TicketStatus
    priority: Priority
    created_at: datetime
    can_reopen: bool
    message_starts_new_ticket: bool  # RO-4: closed, or resolved past the 7-day window
    reopen_until: datetime | None
    messages: list[CustomerMessageOut]


class CustomerWriteOut(BaseModel):
    """POST messages result. RO-4: writing to a closed (or expired) ticket opens a NEW ticket
    whose secret link is returned once; otherwise both fields are null."""

    new_ticket_number: int | None = None
    new_ticket_link: str | None = None
