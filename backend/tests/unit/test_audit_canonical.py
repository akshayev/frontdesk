"""Canonical JSON and payload rules of the audit chain (ARCHITECTURE §8, LEAK-3). No DB."""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.audit.chain import ForbiddenPayloadKeyError, append_event, canonical_json, chain_hash
from app.models import ActorType

T = uuid.UUID("11111111-2222-3333-4444-555555555555")


def test_canonical_json_is_sorted_compact_utc_microseconds() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    out = canonical_json(
        ticket_id=T, actor_type=ActorType.agent, actor_id=None, event_type="claimed",
        payload={"z": 1, "a": [1, 2]}, created_at=datetime(2026, 11, 23, 10, 0, tzinfo=ist),
    )
    assert out == (
        b'{"actor_id":null,"actor_type":"agent","created_at":"2026-11-23T04:30:00.000000+00:00",'
        b'"event_type":"claimed","payload":{"a":[1,2],"z":1},'
        b'"ticket_id":"11111111-2222-3333-4444-555555555555"}'
    )


def test_canonical_json_independent_of_key_order() -> None:
    now = datetime(2026, 11, 23, 4, 30, 0, 123456, tzinfo=UTC)
    kwargs = {"ticket_id": None, "actor_type": "system", "actor_id": None, "event_type": "x",
              "created_at": now}
    a = canonical_json(payload={"b": 1, "a": {"y": 2, "x": 3}}, **kwargs)  # type: ignore[arg-type]
    b = canonical_json(payload={"a": {"x": 3, "y": 2}, "b": 1}, **kwargs)  # type: ignore[arg-type]
    assert a == b
    assert chain_hash(bytes(32), a) == chain_hash(bytes(32), b)
    assert chain_hash(bytes(32), a) != chain_hash(b"\x01" * 32, a)


@pytest.mark.parametrize(
    "payload",
    [{"body": "secret"}, {"note": "x"}, {"text": "x"}, {"Body": "x"},
     {"message": {"body": "nested"}}, {"items": [{"note": "in a list"}]}],
)
def test_append_event_rejects_body_note_text_keys(payload: dict[str, object]) -> None:
    """LEAK-3: rejected before touching the database (the session is never used)."""
    with pytest.raises(ForbiddenPayloadKeyError, match="LEAK-3"):
        append_event(Session(), datetime(2026, 11, 23, tzinfo=UTC), None, ActorType.system,
                     None, "note_added", payload)
