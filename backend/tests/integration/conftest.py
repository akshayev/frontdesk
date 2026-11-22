"""Integration fixtures: a fresh PostgreSQL database per test session (TEST-PLAN: real PG 16).

- `frontdesk_test` is dropped (if left over) and recreated, then `alembic upgrade head` runs on
  it as the OWNER role (MIGRATION_DATABASE_URL), exactly as in production.
- `owner_conn` / `app_conn` are per-test connections (owner role / frontdesk_app) whose
  transaction is rolled back afterwards.
"""

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

from app.config import get_settings

if TYPE_CHECKING:
    from tests.integration.api_support import ApiHarness

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DB = "frontdesk_test"
_SAFE_DB_NAME = re.compile(r"^frontdesk_[a-z_]*test$")


def _owner_url() -> URL:
    url = get_settings().migration_database_url
    assert url is not None, "MIGRATION_DATABASE_URL must be set (see .env.example)"
    return make_url(url.get_secret_value())


def _app_url() -> URL:
    url = get_settings().database_url
    assert url is not None, "DATABASE_URL must be set (see .env.example)"
    return make_url(url.get_secret_value())


def recreate_database(name: str) -> None:
    """Drop (if present) and create a throwaway test database. Only *_test names allowed."""
    assert _SAFE_DB_NAME.match(name), f"refusing to recreate non-test database {name!r}"
    admin = create_engine(_owner_url(), isolation_level="AUTOCOMMIT")
    quoted = admin.dialect.identifier_preparer.quote(name)
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {quoted}"))
    admin.dispose()


def drop_database(name: str) -> None:
    """Drop a throwaway test database. Only *_test names allowed."""
    assert _SAFE_DB_NAME.match(name), f"refusing to drop non-test database {name!r}"
    admin = create_engine(_owner_url(), isolation_level="AUTOCOMMIT")
    quoted = admin.dialect.identifier_preparer.quote(name)
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
    admin.dispose()


def owner_engine_for(name: str) -> Engine:
    """Engine for database `name` as the owner (migration) role."""
    return create_engine(_owner_url().set(database=name))


def run_alembic(engine: Engine, direction: str, target: str) -> None:
    """Run `alembic upgrade|downgrade <target>` on `engine` and commit."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        getattr(command, direction)(cfg, target)


def app_engine_for(name: str) -> Engine:
    """Engine for database `name` as the restricted role frontdesk_app."""
    return create_engine(_app_url().set(database=name))


@contextmanager
def migrated_database(name: str) -> Iterator[tuple[Engine, Engine]]:
    """A fresh, fully migrated throwaway database → (owner engine, app engine).

    Used by tests that need committed data with a clean audit chain (the shared
    `frontdesk_test` database holds a deliberately fake audit row, see `seeded`).
    """
    recreate_database(name)
    owner = owner_engine_for(name)
    app = app_engine_for(name)
    try:
        run_alembic(owner, "upgrade", "head")
        yield owner, app
    finally:
        app.dispose()
        owner.dispose()
        drop_database(name)


@pytest.fixture(scope="session")
def owner_engine() -> Iterator[Engine]:
    """Fresh, fully migrated `frontdesk_test` database; engine connects as the owner role."""
    recreate_database(TEST_DB)
    engine = owner_engine_for(TEST_DB)
    run_alembic(engine, "upgrade", "head")
    yield engine
    engine.dispose()
    drop_database(TEST_DB)


@pytest.fixture(scope="session")
def app_engine(owner_engine: Engine) -> Iterator[Engine]:
    """Engine for `frontdesk_test` connecting as the restricted role frontdesk_app."""
    engine = app_engine_for(TEST_DB)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def seeded(owner_engine: Engine) -> dict[str, object]:
    """One committed row in every table, so row-level triggers have something to fire on."""
    now = datetime(2026, 11, 23, 4, 0, tzinfo=UTC)
    agent_id, customer_id, ticket_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agents (id, email, name, role, password_hash, created_at) "
                "VALUES (:id, 'seed@example.com', 'Seed', 'agent', 'x', :now)"
            ),
            {"id": agent_id, "now": now},
        )
        conn.execute(
            text("INSERT INTO customers (id, name, email) VALUES (:id, 'C', 'c@example.com')"),
            {"id": customer_id},
        )
        conn.execute(
            text(
                "INSERT INTO tickets (id, subject, customer_id, priority, status, created_at, "
                "first_response_due_at, resolution_due_at, customer_token_hash) "
                "VALUES (:id, 'Seed', :cid, 'medium', 'new', :now, :now, :now, :tok)"
            ),
            {"id": ticket_id, "cid": customer_id, "now": now, "tok": b"\x01" * 32},
        )
        conn.execute(
            text(
                "INSERT INTO messages (ticket_id, author_type, body, created_at) "
                "VALUES (:tid, 'customer', 'hello', :now)"
            ),
            {"tid": ticket_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO internal_notes (ticket_id, agent_id, body, created_at) "
                "VALUES (:tid, :aid, 'secret', :now)"
            ),
            {"tid": ticket_id, "aid": agent_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO audit_events (ticket_id, actor_type, event_type, payload, "
                "created_at, prev_hash, hash) "
                "VALUES (:tid, 'system', 'ticket_created', '{}'::jsonb, :now, :z, :h)"
            ),
            {"tid": ticket_id, "now": now, "z": b"\x00" * 32, "h": b"\x02" * 32},
        )
    return {"agent_id": agent_id, "customer_id": customer_id, "ticket_id": ticket_id}


def _rolled_back(engine: Engine) -> Iterator[Connection]:
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        if trans.is_active:
            trans.rollback()
        conn.close()


@pytest.fixture
def owner_conn(owner_engine: Engine, seeded: dict[str, object]) -> Iterator[Connection]:
    """Owner-role connection; everything is rolled back after the test."""
    yield from _rolled_back(owner_engine)


@pytest.fixture
def app_conn(app_engine: Engine, seeded: dict[str, object]) -> Iterator[Connection]:
    """frontdesk_app connection; everything is rolled back after the test."""
    yield from _rolled_back(app_engine)


# --- API fixtures (Sprint 3) ------------------------------------------------------------------
# A fresh migrated database per test module, an app whose request `now` can be frozen and
# moved (ARCHITECTURE §6: tests override the time source), and agents signed in by inserting
# a session row directly (no Argon2, no login rate limit, no 12 h expiry during time travel).


@pytest.fixture(scope="module")
def api_engines(request: pytest.FixtureRequest) -> Iterator[tuple[Engine, Engine]]:
    """(owner engine, app engine) for a throwaway database named after the test module."""
    module = request.module.__name__.rsplit(".", 1)[-1].removeprefix("test_")
    name = "frontdesk_" + re.sub(r"[^a-z_]", "", module) + "_test"
    with migrated_database(name) as engines:
        yield engines


@pytest.fixture
def api(api_engines: tuple[Engine, Engine]) -> Iterator["ApiHarness"]:
    """An ApiHarness with frozen time at Mon 23 Nov 2026 10:00 IST and fresh rate limits."""
    from app.security.ratelimit import limiter
    from tests.integration.api_support import ApiHarness

    limiter.reset()
    yield ApiHarness.build(*api_engines)
    limiter.reset()
