"""T017: AuthService on the seeded temp DB with a frozen clock."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from hcm_lite.models.domain import Role
from tests.conftest import DEMO_PASSWORD


def _db(tmp_path):
    return closing(sqlite3.connect(tmp_path / "hcm_test.db"))


def _audit(tmp_path):
    with _db(tmp_path) as db:
        return db.execute("SELECT action, channel, actor_user_id FROM audit_events"
                          " ORDER BY id").fetchall()


def _failures(tmp_path, user_id="U0001"):
    with _db(tmp_path) as db:
        return db.execute("SELECT COUNT(*) FROM login_failures WHERE user_id=?",
                          (user_id,)).fetchone()[0]


async def test_success_returns_user_and_audits_channel(auth_service, tmp_path):
    user = await auth_service.authenticate("employee", DEMO_PASSWORD, "chat")
    assert user is not None
    assert (user.user_id, user.role, user.employee_id) == ("U0001", Role.EMPLOYEE, "E1001")
    assert user.display_name and user.department
    assert _audit(tmp_path) == [("login_success", "chat", "U0001")]


async def test_wrong_password(auth_service, tmp_path):
    assert await auth_service.authenticate("employee", "wrong", "api") is None
    assert _audit(tmp_path) == [("login_failed", "api", "U0001")]
    assert _failures(tmp_path) == 1


async def test_unknown_user_uses_dummy_hash(auth_service, tmp_path, monkeypatch):
    from hcm_lite.services import auth_service as module

    calls = []
    monkeypatch.setattr(module, "dummy_verify", lambda p: calls.append(p) or False)
    assert await auth_service.authenticate("nobody", "pw", "chat") is None
    assert calls == ["pw"]
    assert _audit(tmp_path) == [("login_failed", "chat", None)]


async def test_lockout_after_five_failures(auth_service, tmp_path, clock):
    for _ in range(5):
        assert await auth_service.authenticate("employee", "wrong", "chat") is None
        clock.advance(minutes=1)
    with _db(tmp_path) as db:
        assert db.execute("SELECT locked_until FROM users WHERE id='U0001'").fetchone()[0]
    # 6th attempt, correct password, still inside the lock
    assert await auth_service.authenticate("employee", DEMO_PASSWORD, "chat") is None
    actions = [a for a, _, _ in _audit(tmp_path)]
    assert actions.count("login_failed") == 5
    assert actions[-1] == "account_locked"
    assert "login_success" not in actions


async def test_lock_expires_then_success_clears_failures(auth_service, tmp_path, clock):
    for _ in range(5):
        await auth_service.authenticate("employee", "wrong", "chat")
    assert _failures(tmp_path) == 5
    clock.advance(minutes=16)
    user = await auth_service.authenticate("employee", DEMO_PASSWORD, "chat")
    assert user is not None
    assert _failures(tmp_path) == 0
    with _db(tmp_path) as db:
        assert db.execute("SELECT locked_until FROM users WHERE id='U0001'").fetchone()[0] is None


async def test_failures_outside_window_do_not_lock(auth_service, clock):
    for _ in range(4):
        await auth_service.authenticate("employee", "wrong", "chat")
    clock.advance(minutes=20)
    await auth_service.authenticate("employee", "wrong", "chat")
    assert await auth_service.authenticate("employee", DEMO_PASSWORD, "chat") is not None


async def test_inactive_user_rejected(auth_service, tmp_path):
    with _db(tmp_path) as db:
        db.execute("UPDATE users SET active=0 WHERE id='U0001'")
        db.commit()
    assert await auth_service.authenticate("employee", DEMO_PASSWORD, "chat") is None
    assert await auth_service.load_user("U0001") is None


async def test_load_user_reflects_role_change(auth_service, tmp_path):
    assert (await auth_service.load_user("U0001")).role == Role.EMPLOYEE
    with _db(tmp_path) as db:
        db.execute("UPDATE users SET role='manager' WHERE id='U0001'")
        db.commit()
    assert (await auth_service.load_user("U0001")).role == Role.MANAGER
    assert await auth_service.load_user("U9999") is None


async def test_tokens_round_trip_and_revoke(auth_service, make_user, tmp_path):
    from hcm_lite.errors import InvalidToken

    token, expires = auth_service.issue_token(make_user(Role.MANAGER))
    assert expires == 3600
    assert auth_service.verify_token(token) == "U0002"
    await auth_service.revoke_token(token)
    with pytest.raises(InvalidToken):
        auth_service.verify_token(token)
    assert _audit(tmp_path) == [("logout", "api", "U0002")]


async def test_record_logout_reasons(auth_service, make_user, tmp_path):
    await auth_service.record_logout(make_user(), "logout")
    await auth_service.record_logout(make_user(), "session_expired")
    assert _audit(tmp_path) == [("logout", "chat", "U0001"), ("session_expired", "chat", "U0001")]


# --------------------------------------------------------------------------- email + password


async def test_authenticate_by_email(auth_service):
    user = await auth_service.authenticate("employee@demo.hcm", DEMO_PASSWORD, "api")
    assert user is not None
    assert user.email == "employee@demo.hcm" and user.role is Role.EMPLOYEE


def _fast_hash(monkeypatch):
    from hcm_lite.services import auth_service as module
    from hcm_lite.services.passwords import hash_password

    monkeypatch.setattr(module, "hash_password", lambda pw: hash_password(pw, iterations=1_000))


async def test_change_password_happy(auth_service, make_user, monkeypatch, tmp_path):
    _fast_hash(monkeypatch)
    user = make_user(Role.EMPLOYEE)
    await auth_service.change_password(user, DEMO_PASSWORD, "newpass12")
    assert await auth_service.authenticate("employee@demo.hcm", "newpass12", "api") is not None
    assert await auth_service.authenticate("employee@demo.hcm", DEMO_PASSWORD, "api") is None
    assert ("password_changed", "api", "U0001") in _audit(tmp_path)


async def test_change_password_wrong_old(auth_service, make_user, monkeypatch):
    _fast_hash(monkeypatch)
    from hcm_lite.errors import ValidationError

    with pytest.raises(ValidationError) as exc:
        await auth_service.change_password(make_user(Role.EMPLOYEE), "wrongpass", "newpass12")
    assert exc.value.field == "old_password"


async def test_change_password_too_short(auth_service, make_user):
    from hcm_lite.errors import ValidationError

    with pytest.raises(ValidationError) as exc:
        await auth_service.change_password(make_user(Role.EMPLOYEE), DEMO_PASSWORD, "short")
    assert exc.value.field == "new_password"
