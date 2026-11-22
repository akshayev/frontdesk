"""scripts/rotate_demo_password.py on a throwaway database (D-047)."""

import hashlib
import secrets
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ActorType, Agent, AgentRole, AuditEvent
from app.models import Session as SessionRow
from app.security.passwords import hash_password, verify_password
from scripts import rotate_demo_password as rot
from scripts import seed
from tests.integration.conftest import migrated_database

OLD = "old-demo-" + secrets.token_hex(8)
NEW = "Rotated7demo" + secrets.token_hex(4) + "x9"


@pytest.fixture(scope="module")
def seeded() -> Iterator[tuple[Engine, Engine]]:
    settings = get_settings().model_copy(update={"seed_demo_password": SecretStr(OLD)})
    with migrated_database("frontdesk_rotate_test") as (owner, app):
        seed.run(settings, engine=app)
        yield owner, app


def _add_session(owner: Engine, email: str) -> None:
    with Session(owner) as s, s.begin():
        agent = s.scalars(select(Agent).where(Agent.email == email)).one()
        now = s.scalar(select(func.now()))
        s.add(SessionRow(agent_id=agent.id, created_at=now, expires_at=now + timedelta(hours=12),
                         token_hash=hashlib.sha256(uuid.uuid4().bytes).digest()))


def _events(owner: Engine) -> list[AuditEvent]:
    with Session(owner) as s:
        return list(s.scalars(select(AuditEvent).where(
            AuditEvent.event_type == "password_rotated").order_by(AuditEvent.id)))


def test_refuses_weak_password(seeded) -> None:
    _, app = seeded
    for weak in ("short1", "onlyletterslonger", "1234567890123456"):
        with pytest.raises(rot.RotationRefused):
            rot.run(app, weak)
    assert _events(seeded[0]) == []


def test_refuses_when_accounts_are_not_the_seeded_eleven(seeded) -> None:
    owner, app = seeded
    with Session(owner) as s, s.begin():
        s.add(Agent(email="extra@arvo.example", name="Extra", role=AgentRole.agent,
                    password_hash=hash_password(OLD), created_at=s.scalar(select(func.now()))))
    try:
        with pytest.raises(rot.RotationRefused, match="found 12"):
            rot.run(app, NEW)
        assert _events(owner) == []
        with Session(owner) as s:  # nothing changed: old password still valid
            meera = s.scalars(select(Agent).where(Agent.email == "meera@arvo.example")).one()
            assert verify_password(meera.password_hash, OLD)
    finally:
        with Session(owner) as s, s.begin():
            s.execute(Agent.__table__.delete().where(Agent.email == "extra@arvo.example"))


def test_rotation_rehashes_unlocks_revokes_and_audits(seeded) -> None:
    owner, app = seeded
    _add_session(owner, "meera@arvo.example")
    _add_session(owner, "priya@arvo.example")
    with Session(owner) as s, s.begin():
        s.execute(update(Agent).where(Agent.email == "rohini@arvo.example").values(
            failed_login_count=5, locked_until=func.now() + timedelta(minutes=15)))

    report, ok, checked = rot.run(app, NEW)

    assert report == rot.RotationReport(accounts_updated=11, sessions_revoked=2)
    assert ok and checked > 80
    with Session(owner) as s:
        agents = list(s.scalars(select(Agent)))
        open_sessions = s.scalar(select(func.count()).select_from(SessionRow).where(
            SessionRow.revoked_at.is_(None)))
    assert len(agents) == 11
    assert all(verify_password(a.password_hash, NEW) for a in agents)
    assert not any(verify_password(a.password_hash, OLD) for a in agents)
    assert len({a.password_hash for a in agents}) == 11  # fresh salt per account
    assert all(a.failed_login_count == 0 and a.locked_until is None for a in agents)
    assert open_sessions == 0

    events = _events(owner)
    assert len(events) == 11
    assert {e.payload["agent_id"] for e in events} == {str(a.id) for a in agents}
    assert all(e.actor_type == ActorType.system and e.actor_id is None and e.ticket_id is None
               and set(e.payload) == {"agent_id"} for e in events)
    assert len({e.created_at for e in events}) == 1  # one transaction, one DB now (D-021)


def test_app_url_from_env_neon(tmp_path: Path) -> None:
    env = tmp_path / ".env.neon"
    env.write_text("NEON_OWNER_URL=postgresql://neondb_owner:ownerpw@host.example:5432/neondb"
                   "?sslmode=require\nNEON_APP_DB_PASSWORD=apppw\n")
    url = rot.app_url_from_env_neon(env)
    assert (url.drivername, url.username, url.password, url.host, url.database) == (
        "postgresql+psycopg", "frontdesk_app", "apppw", "host.example", "neondb")
    assert url.query["sslmode"] == "require"
    env.write_text("NEON_OWNER_URL=postgresql://o:p@h/d\n")
    with pytest.raises(rot.RotationRefused, match="NEON_APP_DB_PASSWORD"):
        rot.app_url_from_env_neon(env)
