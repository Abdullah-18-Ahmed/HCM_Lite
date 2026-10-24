"""T010: PBKDF2-SHA256 password hashing (research D-05)."""

from __future__ import annotations

import pytest

from hcm_lite.services.passwords import ITERATIONS, dummy_verify, hash_password, verify_password


@pytest.fixture(scope="module")
def hashed() -> str:
    return hash_password("correct horse battery staple")


def test_format(hashed):
    assert ITERATIONS == 600_000
    algo, iterations, salt, digest = hashed.split("$")
    assert algo == "pbkdf2_sha256"
    assert iterations == "600000"
    assert salt and digest
    assert len(hashed) <= 200  # users.password_hash is VARCHAR(200)


def test_verify_true_and_false(hashed):
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("correct horse battery stapler", hashed) is False
    assert verify_password("", hashed) is False


def test_unique_salts():
    a, b = hash_password("same"), hash_password("same")
    assert a != b
    assert a.split("$")[2] != b.split("$")[2]
    assert verify_password("same", a) and verify_password("same", b)


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "plaintext",
        "pbkdf2_sha256$600000$onlythree",
        "md5$600000$c2FsdA$aGFzaA",
        "pbkdf2_sha256$notanint$c2FsdA$aGFzaA",
        "pbkdf2_sha256$0$c2FsdA$aGFzaA",
        "pbkdf2_sha256$999999999$c2FsdA$aGFzaA",
        "pbkdf2_sha256$600000$***$***",
        "pbkdf2_sha256$600000$c2FsdA$aGFzaA$extra",
    ],
)
def test_malformed_hash_is_false(stored):
    assert verify_password("anything", stored) is False


def test_non_string_inputs_are_false(hashed):
    assert verify_password(None, hashed) is False  # type: ignore[arg-type]
    assert verify_password("x", None) is False  # type: ignore[arg-type]


def test_dummy_verify_always_false():
    assert dummy_verify("whatever") is False


def test_non_ascii_digit_iterations_rejected(hashed):
    _, _, salt, digest = hashed.split("$")
    assert verify_password("correct horse battery staple",
                           f"pbkdf2_sha256$６００000${salt}${digest}") is False
    assert verify_password("x", f"pbkdf2_sha256$²${salt}${digest}") is False


def test_dummy_hash_built_at_import():
    from hcm_lite.services import passwords
    assert passwords._DUMMY_HASH.startswith("pbkdf2_sha256$600000$")
    assert passwords._dummy_hash() is passwords._DUMMY_HASH
