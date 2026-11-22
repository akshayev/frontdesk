"""Protection: insert-only audit_events, messages, internal_notes (AUD-2, D-015).

forbid_mutation() raises on any UPDATE, DELETE or TRUNCATE. The triggers fire for every
role including the table owner, so even a migration-role session cannot rewrite history
without first dropping the trigger (which itself is a visible schema change).

Revision ID: 0002_protection
Revises: 0001_schema
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_protection"
down_revision: str | None = "0001_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FORBID_MUTATION_SQL = """
CREATE FUNCTION forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% on table % is forbidden: rows are insert-only (AUD-2)',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""

# Written out literally (identifiers cannot be bound parameters; no string formatting).
CREATE_TRIGGERS = (
    "CREATE TRIGGER audit_events_forbid_update_delete BEFORE UPDATE OR DELETE ON audit_events "
    "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()",
    "CREATE TRIGGER audit_events_forbid_truncate BEFORE TRUNCATE ON audit_events "
    "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()",
    "CREATE TRIGGER messages_forbid_update_delete BEFORE UPDATE OR DELETE ON messages "
    "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()",
    "CREATE TRIGGER messages_forbid_truncate BEFORE TRUNCATE ON messages "
    "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()",
    "CREATE TRIGGER internal_notes_forbid_update_delete BEFORE UPDATE OR DELETE ON internal_notes "
    "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()",
    "CREATE TRIGGER internal_notes_forbid_truncate BEFORE TRUNCATE ON internal_notes "
    "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()",
)

DROP_TRIGGERS = (
    "DROP TRIGGER internal_notes_forbid_truncate ON internal_notes",
    "DROP TRIGGER internal_notes_forbid_update_delete ON internal_notes",
    "DROP TRIGGER messages_forbid_truncate ON messages",
    "DROP TRIGGER messages_forbid_update_delete ON messages",
    "DROP TRIGGER audit_events_forbid_truncate ON audit_events",
    "DROP TRIGGER audit_events_forbid_update_delete ON audit_events",
)


def upgrade() -> None:
    """Create forbid_mutation() and attach row + statement triggers (AUD-2)."""
    op.execute(sa.text(FORBID_MUTATION_SQL))
    for stmt in CREATE_TRIGGERS:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    """Remove the triggers and the function."""
    for stmt in DROP_TRIGGERS:
        op.execute(sa.text(stmt))
    op.execute(sa.text("DROP FUNCTION forbid_mutation()"))
