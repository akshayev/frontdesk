"""Argon2id hashing and verification. Implements: SECURITY §2, D-017.

argon2-cffi's PasswordHasher defaults are Argon2id with the library's recommended cost
(RFC 9106 low-memory profile). Verification is constant-time inside the library.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# SECURITY §2 / D-029: for an unknown email we still run one full Argon2 verification, against
# this dummy hash, so "no such account" and "wrong password" take the same time. Hashed
# once at import with the same parameters as real hashes, so the cost is identical.
_DUMMY_HASH = _hasher.hash("frontdesk-timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    """Return an Argon2id hash (salt and parameters encoded in the string)."""
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """SECURITY §2: True only if `password` matches `password_hash`.

    `password_hash=None` (unknown email) verifies against the dummy hash and returns False,
    keeping the response time equal (no account enumeration by timing, D-029).
    """
    if password_hash is None:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except VerificationError:
            pass
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False
