"""I-5, I-6: audit_events, messages, internal_notes are insert-only (AUD-2), enforced by the DB.

Two independent layers are tested:
- grants: frontdesk_app has no UPDATE/DELETE/TRUNCATE privilege (permission denied);
- triggers: even the owner role is stopped by forbid_mutation().
"""

import pytest
from psycopg import errors
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

# Literal statements per table (no SQL string formatting, CLAUDE.md).
MUTATIONS: dict[str, dict[str, str]] = {
    "audit_events": {
        "UPDATE": "UPDATE audit_events SET event_type = 'tampered'",
        "DELETE": "DELETE FROM audit_events",
        "TRUNCATE": "TRUNCATE audit_events",
    },
    "messages": {
        "UPDATE": "UPDATE messages SET body = 'tampered'",
        "DELETE": "DELETE FROM messages",
        "TRUNCATE": "TRUNCATE messages",
    },
    "internal_notes": {
        "UPDATE": "UPDATE internal_notes SET body = 'tampered'",
        "DELETE": "DELETE FROM internal_notes",
        "TRUNCATE": "TRUNCATE internal_notes",
    },
}
OPS = ("UPDATE", "DELETE", "TRUNCATE")


def _expect_refused(conn: Connection, sql: str, message_part: str) -> None:
    with pytest.raises(DBAPIError) as exc_info:
        conn.execute(text(sql))
    assert isinstance(exc_info.value.orig, errors.InsufficientPrivilege)
    assert message_part in str(exc_info.value.orig)


@pytest.mark.parametrize("op", OPS)
def test_i5_app_role_cannot_mutate_audit_events(app_conn: Connection, op: str) -> None:
    """I-5: as frontdesk_app, UPDATE / DELETE / TRUNCATE on audit_events fail."""
    _expect_refused(app_conn, MUTATIONS["audit_events"][op], "permission denied")


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("table", ["messages", "internal_notes"])
def test_i6_app_role_cannot_mutate_messages_and_notes(
    app_conn: Connection, table: str, op: str
) -> None:
    """I-6: as frontdesk_app, UPDATE / DELETE / TRUNCATE on messages, internal_notes fail."""
    _expect_refused(app_conn, MUTATIONS[table][op], "permission denied")


def test_owner_update_audit_events_blocked_by_trigger(owner_conn: Connection) -> None:
    """AUD-2: the trigger stops even the owner role (which has all privileges)."""
    _expect_refused(owner_conn, MUTATIONS["audit_events"]["UPDATE"], "insert-only")


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("table", ["audit_events", "messages", "internal_notes"])
def test_owner_mutations_blocked_by_triggers(owner_conn: Connection, table: str, op: str) -> None:
    """AUD-2: forbid_mutation() fires for UPDATE, DELETE (row) and TRUNCATE (statement)."""
    _expect_refused(owner_conn, MUTATIONS[table][op], "insert-only")


def test_app_role_can_insert_and_read_protected_tables(
    app_conn: Connection, seeded: dict[str, object]
) -> None:
    """Positive control: the protection does not block the normal insert-only workflow."""
    app_conn.execute(
        text(
            "INSERT INTO messages (ticket_id, author_type, body, created_at) "
            "VALUES (:tid, 'customer', 'more', now())"
        ),
        {"tid": seeded["ticket_id"]},
    )
    app_conn.execute(
        text(
            "INSERT INTO audit_events (ticket_id, actor_type, event_type, payload, created_at, "
            "prev_hash, hash) VALUES (:tid, 'customer', 'customer_message', '{}'::jsonb, now(), "
            "'\\x00'::bytea, '\\x01'::bytea)"
        ),
        {"tid": seeded["ticket_id"]},
    )
    count = app_conn.execute(
        text("SELECT count(*) FROM messages WHERE ticket_id = :tid"), {"tid": seeded["ticket_id"]}
    ).scalar_one()
    assert count == 2
