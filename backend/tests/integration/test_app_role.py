"""frontdesk_app has exactly the privileges of ARCHITECTURE §3 / D-023 — no more, no less."""

import pytest
from sqlalchemy import Connection, text

PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")

EXPECTED: dict[str, set[str]] = {
    "audit_events": {"SELECT", "INSERT"},
    "messages": {"SELECT", "INSERT"},
    "internal_notes": {"SELECT", "INSERT"},
    "tickets": {"SELECT", "INSERT", "UPDATE"},
    "agents": {"SELECT", "INSERT", "UPDATE"},
    "customers": {"SELECT", "INSERT", "UPDATE"},
    "sessions": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "holidays": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "alembic_version": set(),
}


@pytest.mark.parametrize("table", sorted(EXPECTED))
def test_app_role_table_privileges(owner_conn: Connection, table: str) -> None:
    """Every table privilege of frontdesk_app matches the §3 grant list exactly."""
    granted = {
        priv
        for priv in PRIVILEGES
        if owner_conn.execute(
            text("SELECT has_table_privilege('frontdesk_app', :t, :p)"),
            {"t": f"public.{table}", "p": priv},
        ).scalar_one()
    }
    assert granted == EXPECTED[table]


def test_app_role_sequences_usage_select(owner_conn: Connection) -> None:
    """USAGE, SELECT on every sequence (ticket number, audit id); never UPDATE (setval)."""
    seqs = owner_conn.execute(
        text("SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = "
             "'public' ORDER BY 1")
    ).scalars().all()
    assert seqs == ["audit_events_id_seq", "tickets_number_seq"]
    for seq in seqs:
        row = owner_conn.execute(
            text(
                "SELECT has_sequence_privilege('frontdesk_app', :s, 'USAGE'), "
                "has_sequence_privilege('frontdesk_app', :s, 'SELECT'), "
                "has_sequence_privilege('frontdesk_app', :s, 'UPDATE')"
            ),
            {"s": f"public.{seq}"},
        ).one()
        assert tuple(row) == (True, True, False)


def test_app_role_attributes(owner_conn: Connection) -> None:
    """D-023: LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT; cannot create in schema."""
    row = owner_conn.execute(
        text(
            "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit, "
            "rolbypassrls, has_schema_privilege('frontdesk_app', 'public', 'CREATE') "
            "FROM pg_roles WHERE rolname = 'frontdesk_app'"
        )
    ).one()
    assert tuple(row) == (True, False, False, False, False, False, False)


def test_app_connection_runs_as_app_role(app_conn: Connection) -> None:
    """DATABASE_URL really logs in as frontdesk_app (not the owner)."""
    assert app_conn.execute(text("SELECT current_user")).scalar_one() == "frontdesk_app"
