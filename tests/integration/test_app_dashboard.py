"""T054: the dashboard sidebar wiring in ``app.py`` (Chainlit mocked, seeded temp DB).

Covers: the sidebar is populated on chat start per role; the ``refresh_dashboard`` action
re-renders after a data change; an idle or deactivated user gets the expiry / sign-in
handling with **no** re-render; an employee's rendered dashboard names no other employee
(end-to-end, T049 semantics: own and own-manager names are part of the profile).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import chainlit as cl

import app as app_module
from tests.integration.conftest import use_scripted_model


def _audit(tmp_path):
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db, db:
        return db.execute(
            "SELECT action, channel, actor_user_id FROM audit_events ORDER BY id"
        ).fetchall()


def _names(tmp_path) -> dict[str, str]:
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db:
        return dict(db.execute("SELECT id, full_name FROM employees").fetchall())


def _elements(calls) -> list[str]:
    return [call[1][0].content for call in calls if call[0] == "elements"]


async def _chat_start(user_id: str, runtime, user_session):
    user_session.set("user", cl.User(identifier=user_id))
    await app_module.on_chat_start()
    return user_session.get(app_module.SESSION_KEY)


async def test_chat_start_populates_sidebar_per_role(runtime, user_session, sent, sidebar):
    session = await _chat_start("U0002", runtime, user_session)  # manager
    assert session is not None
    assert ("title", "Dashboard") in sidebar
    markdown = _elements(sidebar)[0]
    assert "Manager dashboard" in markdown
    assert "Team headcount" in markdown
    assert "Demo data" in markdown
    # the welcome message carries the refresh action
    assert len(sent) == 1
    action = sent[0].kwargs["actions"][0]
    assert action.name == "refresh_dashboard"
    assert action.payload == {}
    assert action.label

    for user_id, heading, present, absent in (
        ("U0001", "Employee dashboard", "My profile", "Team headcount"),
        ("U0003", "HR Administrator dashboard", "Payroll — last month", "My profile"),
    ):
        sidebar.clear()
        await _chat_start(user_id, runtime, user_session)
        markdown = _elements(sidebar)[0]
        assert heading in markdown
        assert present in markdown
        assert absent not in markdown


async def test_refresh_action_rerenders_after_data_change(runtime, user_session, sent,
                                                          sidebar, tmp_path):
    await _chat_start("U0001", runtime, user_session)
    first = _elements(sidebar)[0]
    assert "LR-20261102-TEST" not in first
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db, db:
        db.execute(
            "INSERT INTO leave_requests (id, employee_id, leave_type, start_date, end_date,"
            " working_days, reason, status, source, created_by, created_at, is_demo)"
            " VALUES ('LR-20261102-TEST','E1001','annual','2026-11-02','2026-11-03',2,"
            " 'family event','pending','assistant','U0001','2026-10-25 12:00:00',1)")
    await app_module.refresh_dashboard(
        cl.Action(name="refresh_dashboard", payload={}, label="Refresh dashboard"))
    second = _elements(sidebar)[1]
    assert "LR-20261102-TEST" in second  # the re-render sees the new request
    assert len(sent) == 1  # a refresh posts no chat messages


async def test_refresh_after_idle_expires_without_rerender(runtime, user_session, sent,
                                                           sidebar, tmp_path):
    session = await _chat_start("U0001", runtime, user_session)
    before = len(_elements(sidebar))
    session.last_activity = datetime.now(UTC) - timedelta(minutes=session.idle_minutes + 1)
    use_scripted_model(runtime, ["must never be used"])
    await app_module.refresh_dashboard(
        cl.Action(name="refresh_dashboard", payload={}, label="Refresh dashboard"))
    assert len(_elements(sidebar)) == before  # no re-render
    assert "sign in" in " ".join(str(m.content) for m in sent).lower()
    assert _audit(tmp_path) == [("session_expired", "chat", "U0001")]
    assert user_session.get(app_module.SESSION_KEY) is None


async def test_refresh_after_deactivation_signs_in_message_only(runtime, user_session, sent,
                                                                sidebar, tmp_path):
    await _chat_start("U0001", runtime, user_session)
    before = len(_elements(sidebar))
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db, db:
        db.execute("UPDATE users SET active=0 WHERE id='U0001'")
    await app_module.refresh_dashboard(
        cl.Action(name="refresh_dashboard", payload={}, label="Refresh dashboard"))
    assert len(_elements(sidebar)) == before  # no re-render
    assert "sign in" in sent[-1].content.lower()
    assert _audit(tmp_path) == []  # deactivation is not an audit event


async def test_employee_dashboard_names_no_other_employee(runtime, user_session, sent,
                                                          sidebar, tmp_path):
    await _chat_start("U0001", runtime, user_session)
    markdown = _elements(sidebar)[0]
    names = _names(tmp_path)
    own = names["E1001"]
    manager_name = names["M1002"]  # own manager: part of the profile (T049)
    assert own in markdown
    for employee_id, name in names.items():
        if name in (own, manager_name):
            continue
        assert name not in markdown, f"leaked {employee_id}"
