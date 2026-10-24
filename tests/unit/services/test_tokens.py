"""T012: API JWTs (research D-05, data-model.md §2 ApiToken)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from hcm_lite.errors import ConfigurationError, InvalidToken
from hcm_lite.services.tokens import TokenService

SECRET = "s" * 48
T0 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock() -> Clock:
    return Clock(T0)


@pytest.fixture
def tokens(clock) -> TokenService:
    return TokenService(SECRET, minutes=60, clock=clock)


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def test_issue_verify_roundtrip(tokens):
    token, expires_in = tokens.issue("U0001")
    assert isinstance(token, str)
    assert expires_in == 3600
    assert tokens.verify(token) == "U0001"


def test_claims_are_exactly_sub_iat_exp_jti(tokens):
    token, _ = tokens.issue("U0001")
    claims = _claims(token)
    assert set(claims) == {"sub", "iat", "exp", "jti"}
    assert "role" not in claims
    assert claims["sub"] == "U0001"
    assert claims["iat"] == int(T0.timestamp())
    assert claims["exp"] == int(T0.timestamp()) + 3600
    assert jwt.get_unverified_header(token)["alg"] == "HS256"


def test_unique_jti_per_token(tokens):
    a, _ = tokens.issue("U0001")
    b, _ = tokens.issue("U0001")
    assert _claims(a)["jti"] != _claims(b)["jti"]


def test_expired_token_rejected(tokens, clock):
    token, _ = tokens.issue("U0001")
    clock.advance(minutes=59, seconds=59)
    assert tokens.verify(token) == "U0001"
    clock.advance(seconds=1)
    with pytest.raises(InvalidToken):
        tokens.verify(token)


def test_wrong_key_rejected(tokens, clock):
    other = TokenService("o" * 48, minutes=60, clock=clock)
    token, _ = other.issue("U0001")
    with pytest.raises(InvalidToken):
        tokens.verify(token)


def test_tampered_payload_rejected(tokens):
    token, _ = tokens.issue("U0001")
    header, payload, sig = token.split(".")
    forged = jwt.encode({**_claims(token), "sub": "U0003"}, "x" * 48, algorithm="HS256")
    with pytest.raises(InvalidToken):
        tokens.verify(f"{header}.{forged.split('.')[1]}.{sig}")


def _payload(sub="U0001", **extra) -> dict:
    now = int(T0.timestamp())
    return {"sub": sub, "iat": now, "exp": now + 3600, "jti": "abc", **extra}


def test_alg_none_rejected(tokens):
    token = jwt.encode(_payload(), None, algorithm="none")
    with pytest.raises(InvalidToken):
        tokens.verify(token)


def test_hs512_rejected_even_with_the_right_secret(tokens):
    token = jwt.encode(_payload(), SECRET, algorithm="HS512")
    with pytest.raises(InvalidToken):
        tokens.verify(token)


@pytest.mark.parametrize("missing", ["sub", "iat", "exp", "jti"])
def test_missing_claim_rejected(tokens, missing):
    payload = _payload()
    del payload[missing]
    with pytest.raises(InvalidToken):
        tokens.verify(jwt.encode(payload, SECRET, algorithm="HS256"))


def test_extra_claim_rejected(tokens):
    token = jwt.encode(_payload(role="hr_admin"), SECRET, algorithm="HS256")
    with pytest.raises(InvalidToken):
        tokens.verify(token)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x"])
def test_garbage_rejected(tokens, garbage):
    with pytest.raises(InvalidToken):
        tokens.verify(garbage)


def test_revoked_jti_rejected(tokens):
    token, _ = tokens.issue("U0001")
    other, _ = tokens.issue("U0001")
    tokens.revoke(token)
    with pytest.raises(InvalidToken):
        tokens.verify(token)
    assert tokens.verify(other) == "U0001"  # only that jti is deny-listed


def test_revoke_is_idempotent(tokens):
    token, _ = tokens.issue("U0001")
    tokens.revoke(token)
    tokens.revoke(token)
    with pytest.raises(InvalidToken):
        tokens.verify(token)


def test_revoke_invalid_token_raises(tokens):
    with pytest.raises(InvalidToken):
        tokens.revoke("not-a-token")


def test_deny_list_entries_dropped_after_exp(tokens, clock):
    token, _ = tokens.issue("U0001")
    tokens.revoke(token)
    assert tokens.denied_count == 1
    clock.advance(minutes=61)
    tokens.issue("U0002")  # any call purges expired entries
    assert tokens.denied_count == 0
    with pytest.raises(InvalidToken):  # still invalid: it has expired
        tokens.verify(token)


def test_short_secret_refused():
    with pytest.raises(ConfigurationError):
        TokenService("short", minutes=60)


def test_from_settings_uses_secret_and_minutes(clock):
    class S:
        class api_jwt_secret:  # mimics SecretStr
            @staticmethod
            def get_secret_value():
                return SECRET

        api_token_minutes = 15

    service = TokenService.from_settings(S, clock=clock)
    token, expires_in = service.issue("U0001")
    assert expires_in == 900
    assert service.verify(token) == "U0001"


def test_bool_or_float_iat_exp_rejected(clock):
    now = int(T0.timestamp())
    for iat, exp in ((True, now + 60), (now, float(now + 60)), (now, True)):
        tok = jwt.encode({"sub": "u1", "iat": iat, "exp": exp, "jti": "j"}, SECRET,
                         algorithm="HS256")
        with pytest.raises(InvalidToken):
            TokenService(SECRET, minutes=60, clock=clock).verify(tok)


def test_deny_list_is_thread_safe(tokens):
    import threading
    issued = [tokens.issue("u1")[0] for _ in range(50)]
    threads = [threading.Thread(target=tokens.revoke, args=(t,)) for t in issued]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert tokens.denied_count == 50
    assert hasattr(tokens, "_lock")
