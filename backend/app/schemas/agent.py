"""Request/response models for agent and lead APIs. Implements: UI-2, UI-3, UI-4, CLM-3, RPT-1,
IN-2, AUD-3, SECURITY §6.

Agent-side only: these models may carry notes, SLA dues and audit events. Customer and public
endpoints use app/schemas/customer.py, which is kept strictly separate (LEAK-1, D-022).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import BODY_MAX, SUBJECT_MAX, AgentRole, CloseReason, TicketStatus
from app.sla.policy import BadgeState, Priority, TargetName

Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=BODY_MAX)]
Subject = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                           max_length=SUBJECT_MAX)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Version = Annotated[int, Field(ge=0)]
View = Literal["mine", "unassigned", "all", "late", "waiting"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(_In):
    """POST /api/auth/login body. Password length capped to bound hashing work."""

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class AgentOut(BaseModel):
    """Public view of an agent. Deliberately has no password_hash / lock fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: AgentRole


class AgentListItem(BaseModel):
    """D-040: an agent in the lead's assign dialog — id, name, role only (no email)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: AgentRole


class AgentRef(BaseModel):
    """An agent as shown next to a ticket, message or event."""

    id: uuid.UUID
    name: str


# --- requests --------------------------------------------------------------------------------


class TicketCreateIn(_In):
    """IN-2: an agent records a ticket for a customer who phoned / wrote on WhatsApp."""

    customer_name: Name
    customer_email: EmailStr = Field(max_length=254)
    subject: Subject
    body: Body
    priority: Priority


class VersionIn(_In):
    """CLM-3: the version the agent's screen was showing."""

    expected_version: Version


class ReplyIn(VersionIn):
    """UI-5 "Reply to customer" (+ "and wait for customer", WAIT-2)."""

    body: Body
    wait_for_customer: bool = False


class NoteIn(VersionIn):
    """UI-5 "Internal note" (never shown to the customer, LEAK-1)."""

    body: Body


class PriorityIn(VersionIn):
    """PRI-1..PRI-5 priority change."""

    priority: Priority


class AssignIn(VersionIn):
    """CLM-2: the lead (re)assigns a ticket."""

    agent_id: uuid.UUID


class HolidayIn(_In):
    """SLA-3 / D-014: a lead-editable non-working date (IST calendar date)."""

    date: date
    name: Name


# --- responses -------------------------------------------------------------------------------


class BadgeOut(BaseModel):
    """UI-2 SLA badge: minutes = working minutes left (or overdue when late)."""

    state: BadgeState
    target: TargetName
    minutes: int


class TicketRow(BaseModel):
    """UI-2 list row. `preview` comes from public messages only (UI-3, LEAK-1)."""

    id: uuid.UUID
    number: int
    subject: str
    customer_name: str
    priority: Priority
    status: TicketStatus
    assignee: AgentRef | None
    badge: BadgeOut
    due_at: datetime
    preview: str
    last_activity_at: datetime
    version: int


class TicketCreatedOut(BaseModel):
    """IN-2: the secret customer link is returned ONCE (only its hash is stored)."""

    id: uuid.UUID
    number: int
    customer_link: str


class TargetStatusOut(BaseModel):
    """UI-4 / D-025: one SLA target on the ticket's SLA panel."""

    target: TargetName
    state: BadgeState
    minutes: int
    due_at: datetime
    met_at: datetime | None


class CustomerRef(BaseModel):
    """The ticket's customer, as agents see it."""

    id: uuid.UUID
    name: str
    email: str


class TicketOut(BaseModel):
    """The ticket fields shown on the agent ticket page."""

    id: uuid.UUID
    number: int
    subject: str
    customer: CustomerRef
    priority: Priority
    status: TicketStatus
    assignee: AgentRef | None
    created_at: datetime
    first_response_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    close_reason: CloseReason | None
    parent_ticket_id: uuid.UUID | None
    reopen_count: int
    version: int


class MessageOut(BaseModel):
    """A public message (AUD-4: exact timestamp)."""

    id: uuid.UUID
    author_type: Literal["customer", "agent"]
    author: AgentRef | None
    body: str
    created_at: datetime


class NoteOut(BaseModel):
    """An internal note — agent API only (UI-4: shown in yellow)."""

    id: uuid.UUID
    author: AgentRef
    body: str
    created_at: datetime


class EventOut(BaseModel):
    """AUD-4 timeline entry. Payloads reference ids only (LEAK-3)."""

    id: int
    event_type: str
    actor_type: Literal["agent", "customer", "system"]
    actor_id: uuid.UUID | None
    actor_name: str
    payload: dict[str, Any]
    created_at: datetime


class TicketDetail(BaseModel):
    """UI-4 ticket page: conversation, notes, timeline, SLA panel and the allowed actions."""

    ticket: TicketOut
    targets: list[TargetStatusOut]
    badge: BadgeOut
    messages: list[MessageOut]
    notes: list[NoteOut]
    events: list[EventOut]
    allowed_actions: list[str]
    version: int


class PriorityChangeOut(BaseModel):
    """RPT-1 priority history entry (from priority_changed events)."""

    at: datetime
    from_priority: Priority
    to_priority: Priority


class MissedTargetOut(BaseModel):
    """RPT-1: a missed target and by how many working minutes."""

    target: TargetName
    working_minutes_late: int
    due_at: datetime
    met_at: datetime | None


class LateRowOut(BaseModel):
    """RPT-1 late report row."""

    ticket_id: uuid.UUID
    number: int
    subject: str
    status: TicketStatus
    assignee: AgentRef | None
    initial_priority: Priority
    current_priority: Priority
    priority_history: list[PriorityChangeOut]
    missed: list[MissedTargetOut]
    waiting_on_customer_working_minutes: int


class HolidayOut(BaseModel):
    """A holiday row."""

    model_config = ConfigDict(from_attributes=True)

    date: date
    name: str


class VerifyOut(BaseModel):
    """AUD-3 hash-chain verification result."""

    ok: bool
    checked: int
    first_bad_id: int | None
