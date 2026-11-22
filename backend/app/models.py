"""SQLAlchemy models (ARCHITECTURE §3). Supports: LEAK-2, AUD-2, WAIT-3, RO-1, RO-4.

The schema itself is created by the hand-written Alembic migrations in alembic/versions/;
these models must match them (checked by tests/integration/test_migrations.py).
Timestamps have no server default on purpose: every insert passes the request's DB `now`
(D-021), so a forgotten timestamp fails loudly instead of silently using another clock.
"""

import datetime as dt
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Sequence,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.sla.policy import Priority

BODY_MAX = 10_000
SUBJECT_MAX = 200


class TicketStatus(StrEnum):
    """Ticket lifecycle states (ARCHITECTURE §4)."""

    new = "new"
    open = "open"
    waiting_on_customer = "waiting_on_customer"
    resolved = "resolved"
    closed = "closed"


class CloseReason(StrEnum):
    """Why the system closed a ticket (WAIT-4, RO-3)."""

    no_customer_reply = "no_customer_reply"
    reopen_window_expired = "reopen_window_expired"


class AuthorType(StrEnum):
    """Who wrote a public message."""

    customer = "customer"
    agent = "agent"


class ActorType(StrEnum):
    """Who caused an audit event (AUD-1)."""

    agent = "agent"
    customer = "customer"
    system = "system"


class AgentRole(StrEnum):
    """Agent permission level (D-006)."""

    agent = "agent"
    lead = "lead"


def _pg_enum(cls: type[StrEnum], name: str) -> Enum:
    """Map a StrEnum to an existing PostgreSQL enum type (created by migration 0001)."""
    return Enum(
        cls,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        create_type=False,
        validate_strings=True,
    )


def _ts(nullable: bool = False) -> Any:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


PG_UUID = UUID(as_uuid=True)
UUID_PK = {"primary_key": True, "server_default": text("gen_random_uuid()")}

tickets_number_seq = Sequence("tickets_number_seq", start=1001)


class Base(DeclarativeBase):
    """Declarative base for all Frontdesk tables."""


class Agent(Base):
    """A support agent or the lead."""

    __tablename__ = "agents"
    __table_args__ = (CheckConstraint("email = lower(email)", name="ck_agents_email_lowercase"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID, **UUID_PK)
    email: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[AgentRole] = mapped_column(_pg_enum(AgentRole, "agent_role"))
    password_hash: Mapped[str] = mapped_column(Text)
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = _ts(nullable=True)
    created_at: Mapped[datetime] = _ts()


class Session(Base):
    """Server-side login session; only sha256(token) is stored (SECURITY §2)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID, **UUID_PK)
    agent_id: Mapped[uuid.UUID] = mapped_column(PG_UUID, ForeignKey("agents.id"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    created_at: Mapped[datetime] = _ts()
    expires_at: Mapped[datetime] = _ts()
    revoked_at: Mapped[datetime | None] = _ts(nullable=True)


class Customer(Base):
    """A customer; no account, reaches a ticket through its secret link."""

    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID, **UUID_PK)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)


class Ticket(Base):
    """A support ticket with its SLA clock columns (SLA-*, WAIT-3, RO-1, RO-4, CLM-3)."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(f"char_length(subject) <= {SUBJECT_MAX}", name="ck_tickets_subject_len"),
        CheckConstraint("version >= 0", name="ck_tickets_version_nonneg"),
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_assignee_id", "assignee_id"),
        Index("ix_tickets_resolution_due_at", "resolution_due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID, **UUID_PK)
    number: Mapped[int] = mapped_column(
        BigInteger,
        tickets_number_seq,
        server_default=tickets_number_seq.next_value(),
        unique=True,
    )
    subject: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID, ForeignKey("customers.id"))
    priority: Mapped[Priority] = mapped_column(_pg_enum(Priority, "priority"))
    status: Mapped[TicketStatus] = mapped_column(_pg_enum(TicketStatus, "ticket_status"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID, ForeignKey("agents.id"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = _ts()
    first_response_due_at: Mapped[datetime] = _ts()
    first_response_at: Mapped[datetime | None] = _ts(nullable=True)
    resolution_due_at: Mapped[datetime] = _ts()
    resolution_remaining_min: Mapped[int | None] = mapped_column(Integer)
    paused_at: Mapped[datetime | None] = _ts(nullable=True)
    resolved_at: Mapped[datetime | None] = _ts(nullable=True)
    closed_at: Mapped[datetime | None] = _ts(nullable=True)
    close_reason: Mapped[CloseReason | None] = mapped_column(_pg_enum(CloseReason, "close_reason"))
    parent_ticket_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID, ForeignKey("tickets.id"))
    customer_token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    reopen_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class Message(Base):
    """A PUBLIC message (customer or agent reply). Insert-only (AUD-2)."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(f"char_length(body) <= {BODY_MAX}", name="ck_messages_body_len"),
        Index("ix_messages_ticket_id_created_at", "ticket_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID, **UUID_PK)
    ticket_id: Mapped[uuid.UUID] = mapped_column(PG_UUID, ForeignKey("tickets.id"))
    author_type: Mapped[AuthorType] = mapped_column(_pg_enum(AuthorType, "author_type"))
    author_agent_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID, ForeignKey("agents.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class InternalNote(Base):
    """An AGENT-ONLY note. Never reachable from customer code (LEAK-1, LEAK-2). Insert-only."""

    __tablename__ = "internal_notes"
    __table_args__ = (
        CheckConstraint(f"char_length(body) <= {BODY_MAX}", name="ck_internal_notes_body_len"),
        Index("ix_internal_notes_ticket_id", "ticket_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID, **UUID_PK)
    ticket_id: Mapped[uuid.UUID] = mapped_column(PG_UUID, ForeignKey("tickets.id"))
    agent_id: Mapped[uuid.UUID] = mapped_column(PG_UUID, ForeignKey("agents.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class AuditEvent(Base):
    """Hash-chained, append-only audit record (AUD-1, AUD-2, AUD-3, D-019)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_ticket_id_id", "ticket_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID, ForeignKey("tickets.id"))
    actor_type: Mapped[ActorType] = mapped_column(_pg_enum(ActorType, "actor_type"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID)
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _ts()
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary)
    hash: Mapped[bytes] = mapped_column(LargeBinary)


class Holiday(Base):
    """A non-working date in Asia/Kolkata (SLA-3, D-014). Lead-editable."""

    __tablename__ = "holidays"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID, ForeignKey("agents.id"))
