"""Migrations: full round-trip, seed data, and models == migrated schema."""

from datetime import date

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, text

from app.models import Base

from .conftest import drop_database, owner_engine_for, recreate_database, run_alembic

ROUNDTRIP_DB = "frontdesk_migrations_test"


def _public_tables(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
            ).scalars()
        )


def _public_enum_types(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = 'public' AND t.typtype = 'e' ORDER BY 1"
                )
            ).scalars()
        )


def test_migration_roundtrip_upgrade_downgrade_upgrade() -> None:
    """upgrade head → downgrade base → upgrade head, on a separate throwaway database."""
    recreate_database(ROUNDTRIP_DB)
    engine = owner_engine_for(ROUNDTRIP_DB)
    try:
        run_alembic(engine, "upgrade", "head")
        assert len(_public_tables(engine)) == 9  # 8 tables + alembic_version

        run_alembic(engine, "downgrade", "base")
        assert _public_tables(engine) == ["alembic_version"]
        assert _public_enum_types(engine) == []
        with engine.connect() as conn:
            fn = conn.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'forbid_mutation'")
            ).scalar_one()
            assert fn == 0

        run_alembic(engine, "upgrade", "head")
        assert len(_public_tables(engine)) == 9
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "0004_seed_holidays"
    finally:
        engine.dispose()
        drop_database(ROUNDTRIP_DB)


def test_seed_holidays_exactly_two(owner_engine: Engine) -> None:
    """D-014: only 2026-12-25 and 2027-01-26 are seeded."""
    with owner_engine.connect() as conn:
        rows = conn.execute(text("SELECT date, name FROM holidays ORDER BY date")).all()
    assert [tuple(r) for r in rows] == [
        (date(2026, 12, 25), "Christmas"),
        (date(2027, 1, 26), "Republic Day"),
    ]


def test_models_match_migrated_schema(owner_engine: Engine) -> None:
    """app/models.py and the hand-written migrations describe the same schema."""
    with owner_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    # alembic_version is Alembic's own table and not part of the models.
    diff = [d for d in diff if not (d[0] == "remove_table" and d[1].name == "alembic_version")]
    assert diff == []


def test_ticket_numbers_start_at_1001(owner_engine: Engine) -> None:
    """Tickets display as FD-1001, FD-1002, … (ARCHITECTURE §3)."""
    with owner_engine.connect() as conn:
        start = conn.execute(
            text("SELECT start_value FROM pg_sequences WHERE sequencename = 'tickets_number_seq'")
        ).scalar_one()
    assert start == 1001
