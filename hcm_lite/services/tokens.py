"""API bearer tokens (research D-05, data-model.md §2 ApiToken).

PyJWT HS256 signed with ``API_JWT_SECRET``. Claims are exactly ``sub, iat, exp, jti``; there is
no role claim, so callers always reload the user (``AuthService.load_user``). ``algorithms`` is
always pinned to HS256 (rejects ``alg=none`` and HS512). Revocation is an in-memory ``jti``
deny-list kept until each token's ``exp`` (one API process; see README limitations).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import jwt

from hcm_lite.config import MIN_JWT_SECRET_LENGTH
from hcm_lite.errors import ConfigurationError, InvalidToken

ALGORITHM = "HS256"
CLAIMS = frozenset({"sub", "iat", "exp", "jti"})

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TokenService:
    def __init__(self, secret: str, *, minutes: int, clock: Clock | None = None) -> None:
        if len(secret) < MIN_JWT_SECRET_LENGTH:
            raise ConfigurationError(
                f"API_JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters",
                variables=["API_JWT_SECRET"],
            )
        self._secret = secret
        self._lifetime = minutes * 60
        self._clock = clock or _utc_now
        self._denied: dict[str, int] = {}  # jti -> exp (unix seconds)
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Any, *, clock: Clock | None = None) -> TokenService:
        return cls(settings.api_jwt_secret.get_secret_value(),
                   minutes=settings.api_token_minutes, clock=clock)

    def __repr__(self) -> str:  # never show the secret
        return f"TokenService(lifetime={self._lifetime}s, denied={len(self._denied)})"

    # ------------------------------------------------------------------ helpers

    def _now(self) -> int:
        return int(self._clock().timestamp())

    def _purge(self, now: int) -> None:
        with self._lock:
            for jti in [j for j, exp in self._denied.items() if exp <= now]:
                del self._denied[jti]

    def _decode(self, token: str) -> dict[str, Any]:
        """Check signature, algorithm and the exact claim set. Expiry is checked by callers
        against the injected clock."""
        if not isinstance(token, str) or not token:
            raise InvalidToken("Invalid token")
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],
                options={
                    "require": sorted(CLAIMS),
                    "verify_exp": False,  # checked below with the injectable clock
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
        except jwt.InvalidTokenError:
            raise InvalidToken("Invalid token") from None
        if set(claims) != CLAIMS:
            raise InvalidToken("Invalid token")
        sub, jti, iat, exp = claims["sub"], claims["jti"], claims["iat"], claims["exp"]
        if not (isinstance(sub, str) and sub and isinstance(jti, str) and jti):
            raise InvalidToken("Invalid token")
        if not (type(iat) is int and type(exp) is int and iat <= exp):
            raise InvalidToken("Invalid token")
        return claims

    # ------------------------------------------------------------------ public API

    @property
    def denied_count(self) -> int:
        with self._lock:
            return len(self._denied)

    def issue(self, user_id: str) -> tuple[str, int]:
        """Return ``(jwt, expires_in_seconds)`` for ``user_id``."""
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("user_id is required")
        now = self._now()
        self._purge(now)
        claims = {"sub": user_id, "iat": now, "exp": now + self._lifetime,
                  "jti": uuid.uuid4().hex}
        return jwt.encode(claims, self._secret, algorithm=ALGORITHM), self._lifetime

    def verify(self, token: str) -> str:
        """Return the token's ``sub`` (user id) or raise ``InvalidToken``."""
        claims = self._decode(token)
        now = self._now()
        self._purge(now)
        if now >= claims["exp"]:
            raise InvalidToken("Token expired")
        with self._lock:
            revoked = claims["jti"] in self._denied
        if revoked:
            raise InvalidToken("Token revoked")
        return claims["sub"]

    def revoke(self, token: str) -> None:
        """Deny-list the token's ``jti`` until its ``exp``. An expired token needs no entry."""
        claims = self._decode(token)
        now = self._now()
        self._purge(now)
        if now < claims["exp"]:
            with self._lock:
                self._denied[claims["jti"]] = claims["exp"]
