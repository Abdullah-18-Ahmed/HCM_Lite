"""T043: the Chainlit auth wiring in ``app.py`` (Chainlit mocked, fully offline).

Every handler is called directly against the real ``AuthService`` on a seeded temp SQLite DB.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import chainlit as cl
from agents import RunContextWrapper

import app as app_module
from hcm_lite.assistant.context import AppContext, AppSession
from hcm_lite.assistant.tools import hr_tool
from hcm_lite.models.domain import Role
from tests.conftest import DEMO_PASSWORD
from tests.fakes.scripted_model import ToolCall
from tests.integration.conftest import FakeUserSession, use_scripted_model


def _audit(tmp_path):
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db, db:
        return db.execute(
            "SELECT action, channel, actor_user_id FROM audit_events ORDER BY id"
        ).fetchall()


def _set_role(tmp_path, user_id: str, role: str) -> None:
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db, db:
        db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))


@hr_tool
async def ping(wrapper: RunContextWrapper[AppContext], note: str) -> str:
    # async is required: hr_tool's timeout is only supported for async tools
    return json.dumps({"ok": True, "data": {"note": note}})


async def test_auth_callback_returns_cl_user_only_for_valid_credentials(runtime):
    user = await app_module.password_auth_callback("employee", DEMO_PASSWORD)
    assert isinstance(user, cl.User)
    assert user.identifier == "U0001"
    assert user.metadata["username"] == "employee"
    assert user.metadata["display_name"]
    assert "role" not in user.metadata  # the role is never trusted from metadata
    assert await app_module.password_auth_callback("employee", "not-the-password") is None
    assert await app_module.password_auth_callback("nobody", DEMO_PASSWORD) is None


async def test_starters_role_comes_from_load_user_not_metadata(runtime, tmp_path):
    cl_user = cl.User(identifier="U0001",
                      metadata={"username": "employee", "role": "hr_admin"})
    labels = {s.label for s in await app_module.starters(cl_user)}
    assert "Payroll last month" not in labels  # the spoofed metadata role is ignored
    _set_role(tmp_path, "U0001", "manager")
    labels = {s.label for s in await app_module.starters(cl_user)}
    assert "Who was late today?" in labels  # the DB role change is reflected


async def test_starters_differ_per_role(runtime):
    employee = {s.label for s in await app_module.starters(cl.User(identifier="U0001"))}
    manager = {s.label for s in await app_module.starters(cl.User(identifier="U0002"))}
    hr_admin = {s.label for s in await app_module.starters(cl.User(identifier="U0003"))}
    assert employee < manager and employee < hr_admin and manager != hr_admin
    assert "Who was late today?" in manager - employee
    assert "Payroll last month" in hr_admin - employee
    assert await app_module.starters(cl.User(identifier="U9999")) == []


async def test_chat_start_creates_session_and_welcomes(runtime, user_session, sent):
    user_session.set("user", cl.User(identifier="U0002"))
    await app_module.on_chat_start()
    session = user_session.get(app_module.SESSION_KEY)
    assert isinstance(session, AppSession)
    assert session.user.role == Role.MANAGER
    assert session.idle_minutes == runtime["settings"].session_idle_minutes
    assert len(sent) == 1
    assert "manager" in sent[0].content
    assert "Demo data" in sent[0].content


async def test_inactive_user_is_asked_to_sign_in(runtime, user_session, sent, tmp_path):
    user_session.set("user", cl.User(identifier="U0001"))
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db, db:
        db.execute("UPDATE users SET active=0 WHERE id='U0001'")
    await app_module.on_chat_start()
    assert user_session.get(app_module.SESSION_KEY) is None
    assert "sign in" in sent[0].content.lower()


async def test_each_chat_session_gets_its_own_app_session(runtime, monkeypatch, sent):
    sessions = []
    for _ in range(2):
        fake = FakeUserSession()
        fake.set("user", cl.User(identifier="U0001"))
        monkeypatch.setattr(app_module.cl, "user_session", fake)
        await app_module.on_chat_start()
        sessions.append(fake.get(app_module.SESSION_KEY))
    assert sessions[0] is not sessions[1]
    assert sessions[0].session_id != sessions[1].session_id
    # a turn in session A does not leak history into session B
    use_scripted_model(runtime, ["Reply from session A"])
    fake_a = FakeUserSession()
    fake_a.set("user", cl.User(identifier="U0001"))
    fake_a.set(app_module.SESSION_KEY, sessions[0])
    monkeypatch.setattr(app_module.cl, "user_session", fake_a)
    await app_module.on_message(SimpleNamespace(content="hello"))
    assert sessions[0].history  # the turn was recorded in A
    assert sessions[1].history == []  # B is untouched


async def test_message_runs_turn_with_step_progress(runtime, user_session, sent, steps):
    user_session.set("user", cl.User(identifier="U0001"))
    await app_module.on_chat_start()
    use_scripted_model(runtime, [
        ToolCall("ping", {"note": "progress"}),
        "All done.",
    ], tools=[ping])
    await app_module.on_message(SimpleNamespace(content="run the tool"))
    assert [s.name for s in steps] == ["ping"]
    assert all(s.removed for s in steps)  # closed once the tool finished
    assert sent[-1].content == "All done."
    session = user_session.get(app_module.SESSION_KEY)
    assert session.history  # the turn was appended for the next run


async def test_idle_over_60_minutes_expires_with_message_and_audit(runtime, user_session,
                                                                   sent, tmp_path):
    user_session.set("user", cl.User(identifier="U0001"))
    await app_module.on_chat_start()
    session = user_session.get(app_module.SESSION_KEY)
    assert session.idle_minutes == 60
    session.last_activity = datetime.now(UTC) - timedelta(minutes=61)
    use_scripted_model(runtime, ["must never be used"])
    await app_module.on_message(SimpleNamespace(content="anyone there?"))
    assert "sign in" in " ".join(str(m.content) for m in sent).lower()
    assert _audit(tmp_path) == [("session_expired", "chat", "U0001")]
    assert user_session.get(app_module.SESSION_KEY) is None
    assert session.history == []  # run_turn never ran


async def test_logout_audits_best_effort_and_never_raises(runtime, monkeypatch, tmp_path):
    request = SimpleNamespace(cookies={"access_token": "token-value"})
    monkeypatch.setattr(app_module, "get_token_from_cookies",
                        lambda cookies: cookies.get("access_token"))
    monkeypatch.setattr(app_module, "decode_jwt",
                        lambda token: cl.User(identifier="U0001"))
    await app_module.on_logout(request, SimpleNamespace())
    assert _audit(tmp_path) == [("logout", "chat", "U0001")]
    # no cookie → skipped silently
    monkeypatch.setattr(app_module, "get_token_from_cookies", lambda cookies: None)
    await app_module.on_logout(request, SimpleNamespace())
    # a decode failure → skipped, never raised into the logout response
    def _boom(_token):
        raise ValueError("bad token")
    monkeypatch.setattr(app_module, "get_token_from_cookies",
                        lambda cookies: "token-value")
    monkeypatch.setattr(app_module, "decode_jwt", _boom)
    await app_module.on_logout(request, SimpleNamespace())
    assert _audit(tmp_path) == [("logout", "chat", "U0001")]
