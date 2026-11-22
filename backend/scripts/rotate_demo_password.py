"""Rotate the demo-account password (D-047): `uv run python -m scripts.rotate_demo_password`.

Run from backend/ with NEW_DEMO_PASSWORD in the environment. The database URL is built from
`../.env.neon` (owner URL's host/database + frontdesk_app + NEON_APP_DB_PASSWORD), i.e. the
restricted app role, exactly like the production seed (D-043). `--env-neon PATH` picks another
file. Nothing secret is printed: only counts and the audit verify() result.

In ONE transaction, at the transaction's DB `now` (D-021):
- refuses unless the @arvo.example accounts are exactly the 11 seeded ones (LEADS + AGENTS);
- re-hashes their password (Argon2id, `hash_password`), resets failed_login_count / locked_until;
- revokes every session that is not revoked yet (revoked_at = now);
- appends one `password_rotated` audit event per account: actor system, payload {agent_id}.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, select, update
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from app.audit.chain import append_event, verify
from app.db import RequestContext, request_transaction
from app.models import ActorType, Agent
from app.models import Session as SessionRow
from app.security.passwords import hash_password
from scripts.seed import AGENTS, LEADS

DEMO_DOMAIN = "@arvo.example"
SEEDED_EMAILS = frozenset(email for _, email in LEADS + AGENTS)
MIN_LENGTH = 16


class RotationRefused(RuntimeError):
    """The password is too weak or the accounts are not exactly the seeded ones."""


@dataclass(frozen=True)
class RotationReport:
    """What the rotation changed (counts only, never the password)."""

    accounts_updated: int
    sessions_revoked: int


def check_password(password: str) -> None:
    """D-047: at least 16 characters, with both letters and digits."""
    if len(password) < MIN_LENGTH:
        raise RotationRefused(f"NEW_DEMO_PASSWORD must be at least {MIN_LENGTH} characters")
    if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        raise RotationRefused("NEW_DEMO_PASSWORD must contain letters and digits")


def rotate(ctx: RequestContext, password: str) -> RotationReport:
    """D-047: rotate the 11 seeded accounts' password and revoke all sessions in `ctx`'s
    transaction, auditing one `password_rotated` event (actor system) per account."""
    check_password(password)
    agents = list(ctx.session.scalars(
        select(Agent).where(Agent.email.like(f"%{DEMO_DOMAIN}")).order_by(Agent.email)
        .with_for_update()))
    emails = {agent.email for agent in agents}
    if len(agents) != len(SEEDED_EMAILS) or emails != SEEDED_EMAILS:
        raise RotationRefused(
            f"expected exactly the {len(SEEDED_EMAILS)} seeded {DEMO_DOMAIN} accounts, "
            f"found {len(agents)}")
    for agent in agents:
        agent.password_hash = hash_password(password)  # fresh salt per account
        agent.failed_login_count = 0
        agent.locked_until = None
    ctx.session.flush()
    revoked = ctx.session.execute(
        update(SessionRow).where(SessionRow.revoked_at.is_(None)).values(revoked_at=ctx.now)
        .returning(SessionRow.id)).all()
    for agent in agents:
        append_event(ctx.session, ctx.now, None, ActorType.system, None, "password_rotated",
                     {"agent_id": agent.id})
    return RotationReport(accounts_updated=len(agents), sessions_revoked=len(revoked))


def app_url_from_env_neon(path: Path) -> URL:
    """The frontdesk_app URL: NEON_OWNER_URL's host/port/database/query + the app role."""
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    try:
        owner, app_pw = values["NEON_OWNER_URL"], values["NEON_APP_DB_PASSWORD"]
    except KeyError as missing:
        raise RotationRefused(f"{path.name} has no {missing.args[0]}") from None
    return make_url(owner).set(drivername="postgresql+psycopg", username="frontdesk_app",
                               password=app_pw)


def run(engine: Engine, password: str) -> tuple[RotationReport, bool, int]:
    """Rotate in one transaction, then verify the audit chain in a new one."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with request_transaction(factory) as ctx:
        report = rotate(ctx, password)
    with factory() as session:
        result = verify(session)
    return report, result.ok, result.checked


def main() -> int:
    """CLI entry point; prints counts and verify() only."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-neon", type=Path, default=Path("../.env.neon"))
    args = parser.parse_args()
    password = os.environ.get("NEW_DEMO_PASSWORD", "")
    try:
        check_password(password)
        engine = create_engine(app_url_from_env_neon(args.env_neon))
        report, ok, checked = run(engine, password)
    except RotationRefused as refused:
        print(f"rotation refused: {refused}", file=sys.stderr)
        return 1
    print(f"accounts updated: {report.accounts_updated}")
    print(f"sessions revoked: {report.sessions_revoked}")
    print(f"audit verify: ok={ok} checked={checked}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
