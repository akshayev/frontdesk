"""Schema: tables, enums, indexes (ARCHITECTURE §3).

Hand-written on purpose (no autogenerate). Does not import app.models so it stays frozen
even when the models evolve.

Revision ID: 0001_schema
Revises:
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "priority": ("urgent", "medium", "low"),
    "ticket_status": ("new", "open", "waiting_on_customer", "resolved", "closed"),
    "close_reason": ("no_customer_reply", "reopen_window_expired"),
    "author_type": ("customer", "agent"),
    "actor_type": ("agent", "customer", "system"),
    "agent_role": ("agent", "lead"),
}

TABLES_DROP_ORDER = (
    "audit_events",
    "internal_notes",
    "messages",
    "holidays",
    "tickets",
    "sessions",
    "customers",
    "agents",
)


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _fk_uuid(name: str, target: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target), nullable=nullable
    )


def upgrade() -> None:
    """Create enum types, tables and indexes."""
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=False)

    op.create_table(
        "agents",
        _uuid_pk(),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role", _enum("agent_role"), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("failed_login_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        _ts("locked_until", nullable=True),
        _ts("created_at"),
        sa.CheckConstraint("email = lower(email)", name="ck_agents_email_lowercase"),
    )

    op.create_table(
        "sessions",
        _uuid_pk(),
        _fk_uuid("agent_id", "agents.id"),
        sa.Column("token_hash", sa.LargeBinary, nullable=False, unique=True),
        _ts("created_at"),
        _ts("expires_at"),
        _ts("revoked_at", nullable=True),
    )

    op.create_table(
        "customers",
        _uuid_pk(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=False),
    )

    # bigserial semantics, starting at 1001 so the first ticket shows as FD-1001.
    op.execute(sa.text("CREATE SEQUENCE tickets_number_seq START WITH 1001"))
    op.create_table(
        "tickets",
        _uuid_pk(),
        sa.Column(
            "number",
            sa.BigInteger,
            nullable=False,
            unique=True,
            server_default=sa.text("nextval('tickets_number_seq')"),
        ),
        sa.Column("subject", sa.Text, nullable=False),
        _fk_uuid("customer_id", "customers.id"),
        sa.Column("priority", _enum("priority"), nullable=False),
        sa.Column("status", _enum("ticket_status"), nullable=False),
        _fk_uuid("assignee_id", "agents.id", nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("0")),
        _ts("created_at"),
        _ts("first_response_due_at"),
        _ts("first_response_at", nullable=True),
        _ts("resolution_due_at"),
        sa.Column("resolution_remaining_min", sa.Integer, nullable=True),
        _ts("paused_at", nullable=True),
        _ts("resolved_at", nullable=True),
        _ts("closed_at", nullable=True),
        sa.Column("close_reason", _enum("close_reason"), nullable=True),
        _fk_uuid("parent_ticket_id", "tickets.id", nullable=True),
        sa.Column("customer_token_hash", sa.LargeBinary, nullable=False, unique=True),
        sa.Column("reopen_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("char_length(subject) <= 200", name="ck_tickets_subject_len"),
        sa.CheckConstraint("version >= 0", name="ck_tickets_version_nonneg"),
    )
    op.execute(sa.text("ALTER SEQUENCE tickets_number_seq OWNED BY tickets.number"))
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_assignee_id", "tickets", ["assignee_id"])
    op.create_index("ix_tickets_resolution_due_at", "tickets", ["resolution_due_at"])

    op.create_table(
        "messages",
        _uuid_pk(),
        _fk_uuid("ticket_id", "tickets.id"),
        sa.Column("author_type", _enum("author_type"), nullable=False),
        _fk_uuid("author_agent_id", "agents.id", nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        _ts("created_at"),
        sa.CheckConstraint("char_length(body) <= 10000", name="ck_messages_body_len"),
    )
    op.create_index(
        "ix_messages_ticket_id_created_at", "messages", ["ticket_id", "created_at"]
    )

    op.create_table(
        "internal_notes",
        _uuid_pk(),
        _fk_uuid("ticket_id", "tickets.id"),
        _fk_uuid("agent_id", "agents.id"),
        sa.Column("body", sa.Text, nullable=False),
        _ts("created_at"),
        sa.CheckConstraint("char_length(body) <= 10000", name="ck_internal_notes_body_len"),
    )
    op.create_index("ix_internal_notes_ticket_id", "internal_notes", ["ticket_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),  # BIGSERIAL
        _fk_uuid("ticket_id", "tickets.id", nullable=True),
        sa.Column("actor_type", _enum("actor_type"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        _ts("created_at"),
        sa.Column("prev_hash", sa.LargeBinary, nullable=False),
        sa.Column("hash", sa.LargeBinary, nullable=False),
    )
    op.create_index("ix_audit_events_ticket_id_id", "audit_events", ["ticket_id", "id"])

    op.create_table(
        "holidays",
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        _fk_uuid("created_by", "agents.id", nullable=True),
    )


def downgrade() -> None:
    """Drop tables (indexes and the owned ticket-number sequence go with them), then enums."""
    for table in TABLES_DROP_ORDER:
        op.drop_table(table)
    bind = op.get_bind()
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind, checkfirst=False)
