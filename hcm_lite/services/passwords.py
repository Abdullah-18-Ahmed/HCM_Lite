"""Password hashing: PBKDF2-HMAC-SHA256, 600 000 iterations (research D-05).

Stored format: ``pbkdf2_sha256$<iterations>$<salt>$<hash>`` with URL-safe base64 (no padding).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
MAX_ITERATIONS = 2_000_000  # refuse absurd values from a tampered hash (CPU exhaustion)
SALT_BYTES = 16


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """True only if ``password`` matches ``stored``; any malformed input gives False."""
    if not isinstance(password, str) or not isinstance(stored, str):
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != ALGORITHM:
        return False
    _, iter_text, salt_text, hash_text = parts
    if not (iter_text.isascii() and iter_text.isdecimal()):
        return False
    iterations = int(iter_text)
    if not 1 <= iterations <= MAX_ITERATIONS:
        return False
    try:
        salt, expected = _b64decode(salt_text), _b64decode(hash_text)
    except (binascii.Error, ValueError):
        return False
    if not salt or not expected:
        return False
    return hmac.compare_digest(_derive(password, salt, iterations), expected)


# Built once at import so the first unknown-username check is not faster than later ones.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _dummy_hash() -> str:
    return _DUMMY_HASH


def dummy_verify(password: str) -> bool:
    """Spend the same time as a real check, for unknown usernames (timing parity). Always False."""
    verify_password(password if isinstance(password, str) else "", _dummy_hash())
    return False
