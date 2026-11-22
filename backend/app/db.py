"""Engine, request transaction, request DB 'now' (ARCHITECTURE §6). Supports: SLA-3, AUD-1, AUD-4.

One HTTP request = one database transaction (D-021):
  BEGIN; SET LOCAL statement_timeout = '5s'; SELECT now()  →  RequestContext(now, session)
  … all domain logic and audit events of the request use that single `now` …
  COMMIT on success, ROLLBACK on any exception.

`get_tx` is used with `Depends(get_tx, scope="function")` (see `Tx`) so the COMMIT runs
before the response is sent: a failed commit becomes an error response, never a 200 for
data that was not stored.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Holiday

STATEMENT_TIMEOUT_SQL = "SET LOCAL statement_timeout = '5s'"


@dataclass(frozen=True)
class RequestContext:
    """The request's transaction and its single DB clock value (ARCHITECTURE §6)."""

    now: datetime
    session: Session


def build_engine(settings: Settings) -> Engine:
    """Engine for the restricted app role (DATABASE_URL). Small pool: one process (§1)."""
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_size=5,
        max_overflow=2,
        pool_pre_ping=True,
    )


def session_factory(app: FastAPI) -> sessionmaker[Session]:
    """The app's sessionmaker; the engine is created lazily on first use."""
    factory: sessionmaker[Session] | None = getattr(app.state, "session_factory", None)
    if factory is None:
        engine: Engine | None = getattr(app.state, "engine", None)
        if engine is None:
            engine = build_engine(app.state.settings)
            app.state.engine = engine
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        app.state.session_factory = factory
    return factory


@contextmanager
def request_transaction(factory: sessionmaker[Session]) -> Iterator[RequestContext]:
    """D-021: BEGIN, 5 s statement timeout, `SELECT now()`; commit on success, else rollback."""
    with factory() as session, session.begin():
        session.execute(text(STATEMENT_TIMEOUT_SQL))
        now: datetime = session.execute(text("SELECT now()")).scalar_one()
        yield RequestContext(now=now, session=session)


def get_tx(request: Request) -> Iterator[RequestContext]:
    """FastAPI dependency: one transaction per request (ARCHITECTURE §6)."""
    with request_transaction(session_factory(request.app)) as ctx:
        yield ctx


Tx = Annotated[RequestContext, Depends(get_tx, scope="function")]


def load_holidays(session: Session) -> frozenset[date]:
    """SLA-3: the lead-editable holiday dates, loaded once per request."""
    return frozenset(session.scalars(select(Holiday.date)))
