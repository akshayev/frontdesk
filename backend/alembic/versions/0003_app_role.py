"""Restricted application role frontdesk_app and its grants (D-015, D-023, ARCHITECTURE §3).

The password comes from env APP_DB_PASSWORD. It is handed to PostgreSQL as a bound
parameter (set_config, transaction-local) and quoted server-side with format('%L'); it is
never put into a SQL string in Python.

IMPORTANT for future migrations: this migration grants on the tables that exist NOW and does
not use ALTER DEFAULT PRIVILEGES. Every later migration that creates a table or sequence
MUST grant frontdesk_app exactly the privileges it needs, explicitly, in that migration.

Revision ID: 0003_app_role
Revises: 0002_protection
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.config import get_settings

revision: str = "0003_app_role"
down_revision: str | None = "0002_protection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Creates the role if missing; if it already exists (roles are cluster-wide, e.g. the test
# database shares the cluster with the dev database) only its password is re-synced to
# APP_DB_PASSWORD. Either way the role must end up with no elevated attributes.
ENSURE_ROLE_SQL = """
DO $$
DECLARE
    r pg_roles%ROWTYPE;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'frontdesk_app') THEN
        EXECUTE format(
            'CREATE ROLE frontdesk_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT '
            'PASSWORD %L',
            current_setting('fd.app_pw'));
    ELSE
        EXECUTE format('ALTER ROLE frontdesk_app LOGIN PASSWORD %L', current_setting('fd.app_pw'));
    END IF;
    SELECT * INTO r FROM pg_roles WHERE rolname = 'frontdesk_app';
    IF r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolinherit OR r.rolbypassrls
       OR r.rolreplication THEN
        RAISE EXCEPTION 'frontdesk_app exists with elevated attributes; refusing to continue';
    END IF;
END
$$
"""

UPGRADE_SQL = (
    # Start from nothing: no implicit PUBLIC access to any schema object.
    "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC",
    "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC",
    "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC",
    "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
    # Idempotent: wipe anything frontdesk_app had, then grant exactly §3.
    "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM frontdesk_app",
    "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM frontdesk_app",
    "DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO frontdesk_app', "
    "current_database()); END $$",
    "GRANT USAGE ON SCHEMA public TO frontdesk_app",
    "GRANT SELECT, INSERT ON audit_events, messages, internal_notes TO frontdesk_app",
    "GRANT SELECT, INSERT, UPDATE ON tickets, agents, customers, sessions, holidays "
    "TO frontdesk_app",
    "GRANT DELETE ON holidays, sessions TO frontdesk_app",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO frontdesk_app",
)

DOWNGRADE_SQL = (
    "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM frontdesk_app",
    "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM frontdesk_app",
    "REVOKE USAGE ON SCHEMA public FROM frontdesk_app",
    "DO $$ BEGIN EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM frontdesk_app', "
    "current_database()); END $$",
    # Restore the PostgreSQL default (functions are executable by PUBLIC).
    "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO PUBLIC",
    # Roles are cluster-wide: drop it only if no other database still grants it anything.
    """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'frontdesk_app') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_shdepend d JOIN pg_roles r ON r.oid = d.refobjid
            WHERE r.rolname = 'frontdesk_app' AND d.refclassid = 'pg_authid'::regclass
        ) THEN
            DROP ROLE frontdesk_app;
        ELSE
            RAISE NOTICE 'frontdesk_app kept: still referenced by another database';
        END IF;
    END IF;
END
$$
""",
)


def upgrade() -> None:
    """Ensure role frontdesk_app exists (D-023) and grant exactly ARCHITECTURE §3."""
    password = get_settings().app_db_password
    if password is None or not password.get_secret_value():
        raise RuntimeError("APP_DB_PASSWORD is not set; cannot create role frontdesk_app")
    bind = op.get_bind()
    bind.execute(
        sa.text("SELECT set_config('fd.app_pw', :pw, true)"),
        {"pw": password.get_secret_value()},
    )
    bind.execute(sa.text(ENSURE_ROLE_SQL))
    bind.execute(sa.text("SELECT set_config('fd.app_pw', '', true)"))
    for stmt in UPGRADE_SQL:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    """Revoke every grant in this database; drop the role if nothing else uses it."""
    for stmt in DOWNGRADE_SQL:
        op.execute(sa.text(stmt))
