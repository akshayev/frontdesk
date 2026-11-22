"""AUD-3 hash chain on real PostgreSQL: valid after N appends, valid under concurrent appends,
tampering detected (I-7). Plus the request transaction of ARCHITECTURE §6 (D-021).

Runs on its own throwaway databases so the chain starts empty and committed rows are real.
"""

import threading
import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.audit.chain import GENESIS_HASH, append_event, verify
from app.db import load_holidays, request_transaction
from app.models import ActorType, AuditEvent, Holiday
from tests.integration.conftest import migrated_database


@pytest.fixture(scope="module")
def audit_db() -> Iterator[tuple[Engine, Engine]]:
    with migrated_database("frontdesk_audit_test") as engines:
        yield engines


@pytest.fixture
def app_factory(audit_db: tuple[Engine, Engine]) -> sessionmaker[Session]:
    return sessionmaker(bind=audit_db[1], expire_on_commit=False)


def _append_one(factory: sessionmaker[Session], n: int, ticket_id: uuid.UUID | None = None) -> int:
    """One request-shaped transaction that appends one event; returns the new event id."""
    with request_transaction(factory) as ctx:
        row = append_event(ctx.session, ctx.now, ticket_id, ActorType.system, None,
                           "status_changed", {"n": n, "ref": uuid.uuid4()})
        return row.id


def test_chain_valid_after_n_appends(app_factory: sessionmaker[Session]) -> None:
    """AUD-3: N sequential appends (as frontdesk_app) → verify ok, every row checked."""
    with app_factory() as s:
        before = s.scalar(select(func.count()).select_from(AuditEvent)) or 0
    for n in range(25):
        _append_one(app_factory, n)
    with app_factory() as s:
        first = s.scalars(select(AuditEvent).order_by(AuditEvent.id).limit(1)).one()
        assert bytes(first.prev_hash) == GENESIS_HASH
        assert verify(s).__dict__ == {"ok": True, "checked": before + 25, "first_bad_id": None}


def test_chain_valid_under_concurrent_appends(app_factory: sessionmaker[Session]) -> None:
    """Two threads appending at the same time still produce one linear, valid chain
    (pg_advisory_xact_lock serialises appends)."""
    per_thread = 30
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(offset: int) -> None:
        try:
            barrier.wait()
            for n in range(per_thread):
                _append_one(app_factory, offset + n)
        except BaseException as exc:  # surfaced in the main thread below
            errors.append(exc)

    with app_factory() as s:
        before = s.scalar(select(func.count()).select_from(AuditEvent)) or 0
    threads = [threading.Thread(target=worker, args=(k * 1000,)) for k in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors
    with app_factory() as s:
        result = verify(s)
        assert result.ok and result.checked == before + 2 * per_thread
        prevs = s.scalars(select(AuditEvent.prev_hash)).all()
        assert len(set(map(bytes, prevs))) == len(prevs)  # no fork: every prev used once


def test_request_transaction_db_clock_timeout_and_rollback(
    app_factory: sessionmaker[Session],
) -> None:
    """§6 / D-021: one `now` per transaction, 5 s statement timeout, rollback on error."""
    with request_transaction(app_factory) as ctx:
        assert ctx.session.execute(text("SHOW statement_timeout")).scalar_one() == "5s"
        assert ctx.now.tzinfo is not None
        assert ctx.session.execute(text("SELECT now()")).scalar_one() == ctx.now
        assert load_holidays(ctx.session) == frozenset({date(2026, 12, 25), date(2027, 1, 26)})

    marker = date(2099, 3, 3)
    with pytest.raises(RuntimeError), request_transaction(app_factory) as ctx:
        ctx.session.add(Holiday(date=marker, name="rolled back"))
        ctx.session.flush()
        raise RuntimeError("boom")
    with app_factory() as s:
        assert s.get(Holiday, marker) is None


@pytest.fixture
def tamper_db() -> Iterator[tuple[Engine, Engine]]:
    with migrated_database("frontdesk_tamper_test") as engines:
        yield engines


def _set_row_trigger(owner: Engine, enabled: bool) -> None:
    # Literal DDL per state, no SQL string formatting (CLAUDE.md).
    sql = (
        "ALTER TABLE audit_events ENABLE TRIGGER audit_events_forbid_update_delete"
        if enabled
        else "ALTER TABLE audit_events DISABLE TRIGGER audit_events_forbid_update_delete"
    )
    with owner.begin() as conn:
        conn.execute(text(sql))


def test_i7_tampered_payload_detected(tamper_db: tuple[Engine, Engine]) -> None:
    """I-7: owner disables the row trigger, edits one payload, re-enables → verify reports
    ok=false with exactly that row's id."""
    owner, app = tamper_db
    factory = sessionmaker(bind=app, expire_on_commit=False)
    ids = [_append_one(factory, n) for n in range(5)]
    victim = ids[2]
    with factory() as s:
        assert verify(s).ok
    try:
        _set_row_trigger(owner, enabled=False)
        with owner.begin() as conn:
            conn.execute(
                text("UPDATE audit_events SET payload = '{\"n\": 999}'::jsonb WHERE id = :id"),
                {"id": victim},
            )
    finally:
        _set_row_trigger(owner, enabled=True)
    with factory() as s:
        assert verify(s).__dict__ == {"ok": False, "checked": 3, "first_bad_id": victim}


def test_deleted_row_detected(tamper_db: tuple[Engine, Engine]) -> None:
    """AUD-3: deleting a row breaks the link of the row after it."""
    owner, app = tamper_db
    factory = sessionmaker(bind=app, expire_on_commit=False)
    ids = [_append_one(factory, n) for n in range(4)]
    try:
        _set_row_trigger(owner, enabled=False)
        with owner.begin() as conn:
            conn.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": ids[1]})
    finally:
        _set_row_trigger(owner, enabled=True)
    with factory() as s:
        result = verify(s)
        assert not result.ok and result.first_bad_id == ids[2]
