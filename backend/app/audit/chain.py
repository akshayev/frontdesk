"""append_event(), canonical JSON, sha256 hash chain, verify(). Implements: AUD-1, AUD-2, AUD-3,
LEAK-3 (ARCHITECTURE §8, D-015, D-019, D-021).

Every audit row stores prev_hash (the hash of the row before it, or 32 zero bytes for the
first row) and hash = sha256(prev_hash + canonical_json(row)). Changing any stored field of
any row, or removing / reordering rows, breaks the chain from that row on; verify() finds
the first such row. Tamper-evident, not tamper-proof (SECURITY §7).
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from app.models import ActorType, AuditEvent

# Fixed key for pg_advisory_xact_lock: serialises chain appends across all connections and
# processes; released automatically at COMMIT / ROLLBACK. ASCII "FDAUDIT1" as a bigint.
CHAIN_LOCK_KEY = int.from_bytes(b"FDAUDIT1", "big")
GENESIS_HASH = bytes(32)
# LEAK-3: note (or message) bodies must never be copied into an event payload. Events
# reference ids only; these key names are refused at any nesting depth.
FORBIDDEN_PAYLOAD_KEYS = frozenset({"body", "note", "text"})
_VERIFY_BATCH = 500


class ForbiddenPayloadKeyError(ValueError):
    """An audit payload tried to carry a body/note/text field (LEAK-3)."""


@dataclass(frozen=True)
class VerifyResult:
    """AUD-3: outcome of verify(). `checked` counts the rows examined (it stops at the
    first bad row); `first_bad_id` is None when the whole chain is intact."""

    ok: bool
    checked: int
    first_bad_id: int | None


def _json_default(value: object) -> str:
    """UUIDs are serialised as their canonical string form."""
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"audit payload value of type {type(value).__name__} is not JSON-safe")


def _check_payload_keys(value: object, path: str = "payload") -> None:
    """LEAK-3: refuse body/note/text keys anywhere in the payload (case-insensitive)."""
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if str(key).lower() in FORBIDDEN_PAYLOAD_KEYS:
                raise ForbiddenPayloadKeyError(
                    f"audit payload key {path}.{key!r} is not allowed: events must reference "
                    "messages/notes by id, never carry their text (LEAK-3)"
                )
            _check_payload_keys(inner, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, inner in enumerate(value):
            _check_payload_keys(inner, f"{path}[{index}]")


def _iso_utc(moment: datetime) -> str:
    """created_at in the canonical form: UTC, ISO-8601, always with microseconds."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("audit created_at must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def canonical_json(
    *,
    ticket_id: uuid.UUID | None,
    actor_type: ActorType | str,
    actor_id: uuid.UUID | None,
    event_type: str,
    payload: Mapping[str, Any],
    created_at: datetime,
) -> bytes:
    """AUD-3: the exact bytes that are hashed (§8 step 3).

    sort_keys + compact separators make the output independent of dict order and spacing,
    so the value recomputed from the JSONB column in verify() is byte-identical.
    """
    document = {
        "ticket_id": None if ticket_id is None else str(ticket_id),
        "actor_type": str(ActorType(actor_type).value),
        "actor_id": None if actor_id is None else str(actor_id),
        "event_type": event_type,
        "payload": payload,
        "created_at": _iso_utc(created_at),
    }
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), default=_json_default
    ).encode("utf-8")


def chain_hash(prev_hash: bytes, canonical: bytes) -> bytes:
    """AUD-3: hash = sha256(prev_hash + canonical_bytes)."""
    return hashlib.sha256(prev_hash + canonical).digest()


def append_event(
    session: Session,
    now: datetime,
    ticket_id: uuid.UUID | None,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
    event_type: str,
    payload: Mapping[str, Any],
) -> AuditEvent:
    """AUD-1, AUD-3, LEAK-3, D-021: append one hash-chained event inside the caller's
    transaction, timestamped with the request's DB `now`.

    Steps (§8): advisory xact lock → previous hash (or 32 zero bytes) → canonical JSON →
    sha256(prev + canonical) → INSERT with created_at = now. The lock is held until the
    caller's transaction ends, so concurrent requests append strictly one after another.
    """
    _check_payload_keys(payload)
    # Normalise to plain JSON types (UUID → str) so what is hashed is exactly what JSONB
    # stores and verify() reads back.
    normalised: dict[str, Any] = json.loads(json.dumps(dict(payload), default=_json_default))

    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CHAIN_LOCK_KEY})
    prev_hash = session.scalar(
        select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)
    )
    prev = GENESIS_HASH if prev_hash is None else bytes(prev_hash)
    canonical = canonical_json(
        ticket_id=ticket_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        payload=normalised,
        created_at=now,
    )
    row = session.scalars(
        insert(AuditEvent)
        .values(
            ticket_id=ticket_id,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=event_type,
            payload=normalised,
            created_at=now,
            prev_hash=prev,
            hash=chain_hash(prev, canonical),
        )
        .returning(AuditEvent)
    ).one()
    return row


def verify(session: Session) -> VerifyResult:
    """AUD-3: recompute the chain in id order, streaming; stop at the first bad row.

    A row is bad if its prev_hash is not the previous row's hash (deleted / reordered /
    inserted rows) or its hash does not match its own recomputed content (edited row).
    """
    expected_prev = GENESIS_HASH
    checked = 0
    rows = session.execute(
        select(
            AuditEvent.id,
            AuditEvent.ticket_id,
            AuditEvent.actor_type,
            AuditEvent.actor_id,
            AuditEvent.event_type,
            AuditEvent.payload,
            AuditEvent.created_at,
            AuditEvent.prev_hash,
            AuditEvent.hash,
        )
        .order_by(AuditEvent.id)
        .execution_options(yield_per=_VERIFY_BATCH)
    )
    for row in rows:
        checked += 1
        canonical = canonical_json(
            ticket_id=row.ticket_id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            event_type=row.event_type,
            payload=row.payload,
            created_at=row.created_at,
        )
        stored_prev, stored_hash = bytes(row.prev_hash), bytes(row.hash)
        if stored_prev != expected_prev or stored_hash != chain_hash(stored_prev, canonical):
            rows.close()
            return VerifyResult(ok=False, checked=checked, first_bad_id=row.id)
        expected_prev = stored_hash
    return VerifyResult(ok=True, checked=checked, first_bad_id=None)
