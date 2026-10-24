"""T015: demo seed (research D-13) against a migrated temp SQLite DB."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date, timedelta

import pytest

from hcm_lite.db.seed import (
    DEMO_USERNAMES,
    SeedRefused,
    build_demo_data,
    last_working_day,
    run_seed,
)
from hcm_lite.services.passwords import hash_password, verify_password
from hcm_lite.services.periods import working_days

TODAY = date(2026, 10, 25)  # a Sunday
DEMO_TABLES = (
    "departments", "employees", "users", "attendance", "leave_types", "leave_balances",
    "leave_requests", "payroll_totals", "holidays",
)


def fast_hash(password: str) -> str:
    return hash_password(password, iterations=1_000)


def _db(tmp_path):
    return closing(sqlite3.connect(tmp_path / "hcm_test.db"))


async def _seed(engine, **kwargs):
    kwargs.setdefault("today", TODAY)
    kwargs.setdefault("hasher", fast_hash)
    return await run_seed(engine, **kwargs)


def _count(conn, table, where="1=1"):
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]


async def test_seed_counts_and_demo_accounts(engine, migrated_db, tmp_path):
    report = await _seed(engine)
    with _db(tmp_path) as conn:
        assert _count(conn, "departments") == 6
        assert _count(conn, "employees") == 60
        assert _count(conn, "leave_types") == 5
        users = conn.execute(
            "SELECT username, role, employee_id, is_demo FROM users ORDER BY id"
        ).fetchall()
        assert users == [("employee", "employee", "E1001", 1), ("manager", "manager", "M1002", 1),
                         ("hr_admin", "hr_admin", "H1003", 1)]
        assert conn.execute("SELECT manager_id FROM employees WHERE id='E1001'").fetchone() == (
            "M1002",
        )
        assert _count(conn, "employees", "manager_id='M1002'") >= 3
        assert _count(conn, "attendance") > 0
        assert _count(conn, "payroll_totals") == 6 * 3  # Aug, Sep, Oct
        for table in DEMO_TABLES:
            assert _count(conn, table, "is_demo = 0") == 0, table
            assert report.counts[table] == _count(conn, table), table
    assert DEMO_USERNAMES == ("employee", "manager", "hr_admin")


async def test_seed_is_deterministic_for_the_same_today():
    a, b = build_demo_data(TODAY), build_demo_data(TODAY)
    assert a.employees == b.employees
    assert a.attendance == b.attendance
    assert a.leave_requests == b.leave_requests
    assert a.payroll == b.payroll


async def test_demo_passwords_are_generated_and_printed_once(engine, migrated_db, tmp_path):
    report = await _seed(engine)
    creds = {c.username: c for c in report.credentials}
    assert set(creds) == set(DEMO_USERNAMES)
    assert len({c.password for c in report.credentials}) == 3
    with _db(tmp_path) as conn:
        for username, cred in creds.items():
            stored = conn.execute(
                "SELECT password_hash FROM users WHERE username=?", (username,)
            ).fetchone()[0]
            assert cred.password not in stored
            assert verify_password(cred.password, stored)
    # not constants: a second (reset) run produces new passwords
    again = await _seed(engine, reset=True)
    assert {c.password for c in again.credentials}.isdisjoint({c.password for c in creds.values()})


@pytest.mark.parametrize(
    ("today", "expected_end"),
    [
        (date(2026, 10, 25), date(2026, 10, 23)),  # Sunday -> Friday
        (date(2026, 10, 24), date(2026, 10, 23)),  # Saturday -> Friday
        (date(2026, 10, 26), date(2026, 10, 26)),  # Monday -> today (inclusive)
        (date(2026, 8, 14), date(2026, 8, 13)),  # demo holiday (Friday) -> Thursday
    ],
)
async def test_attendance_ends_on_last_working_day(engine, migrated_db, tmp_path, today,
                                                   expected_end):
    report = await _seed(engine, today=today)
    assert report.attendance_end == expected_end
    with _db(tmp_path) as conn:
        first, last = conn.execute("SELECT MIN(date), MAX(date) FROM attendance").fetchone()
        weekend = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE strftime('%w', date) IN ('0','6')"
        ).fetchone()[0]
        on_holiday = _count(conn, "attendance", "date IN (SELECT date FROM holidays)")
    assert date.fromisoformat(last) == expected_end
    assert date.fromisoformat(first).replace(day=1) <= today.replace(day=1)
    assert weekend == 0 and on_holiday == 0


def test_last_working_day_helper():
    holidays = {date(2026, 8, 14)}
    assert last_working_day(date(2026, 10, 25), holidays) == date(2026, 10, 23)
    assert last_working_day(date(2026, 8, 17), holidays) == date(2026, 8, 17)
    assert last_working_day(date(2026, 8, 16), holidays) == date(2026, 8, 13)


async def test_leave_requests_cover_current_month(engine, migrated_db, tmp_path):
    await _seed(engine)
    month_start = TODAY.replace(day=1)
    month_end = date(2026, 10, 31)
    with _db(tmp_path) as conn:
        rows = conn.execute(
            "SELECT id, employee_id, leave_type, start_date, end_date, working_days, status,"
            " source, created_at FROM leave_requests"
        ).fetchall()
        holidays = {date.fromisoformat(r[0]) for r in conn.execute("SELECT date FROM holidays")}
    reqs = [
        dict(id=r[0], emp=r[1], type=r[2], start=date.fromisoformat(r[3]),
             end=date.fromisoformat(r[4]), days=r[5], status=r[6], source=r[7], created=r[8])
        for r in rows
    ]
    assert {r["status"] for r in reqs} >= {"pending", "approved", "rejected"}
    assert all(r["source"] == "seed" for r in reqs)
    in_month = [r for r in reqs if r["start"] <= month_end and r["end"] >= month_start]
    pending_in_month = [r for r in in_month if r["status"] == "pending"]
    assert len(pending_in_month) >= 2
    future_in_month = [r for r in in_month if r["start"] > TODAY and r["end"] <= month_end]
    assert future_in_month, "at least one future request within the current month"
    assert any(r["emp"] == "E1001" and r["status"] == "pending" for r in reqs)
    assert any(r["emp"] in _team(tmp_path, "M1002") and r["status"] == "pending"
               for r in pending_in_month)
    for r in reqs:
        assert r["end"] >= r["start"]
        assert r["days"] == working_days(r["start"], r["end"], holidays) >= 1
        assert r["id"].startswith("LR-") and len(r["id"]) == 16
        assert date.fromisoformat(r["created"][:10]) <= TODAY


def _team(tmp_path, manager_id):
    with _db(tmp_path) as conn:
        return {r[0] for r in conn.execute(
            "SELECT id FROM employees WHERE manager_id=?", (manager_id,))}


async def test_approved_leave_matches_attendance_and_balances(engine, migrated_db, tmp_path):
    report = await _seed(engine)
    with _db(tmp_path) as conn:
        approved = conn.execute(
            "SELECT employee_id, leave_type, start_date, end_date, working_days"
            " FROM leave_requests WHERE status='approved'"
        ).fetchall()
        leave_days = {(r[0], r[1]) for r in conn.execute(
            "SELECT employee_id, date FROM attendance WHERE status='leave'")}
        balances = {(r[0], r[1]): (float(r[2]), float(r[3])) for r in conn.execute(
            "SELECT employee_id, leave_type, entitled, used FROM leave_balances WHERE year=2026")}
        holidays = {date.fromisoformat(r[0]) for r in conn.execute("SELECT date FROM holidays")}
    used = defaultdict(float)
    expected_leave_days = set()
    for emp, lt, start, end, days in approved:
        used[(emp, lt)] += days
        d = date.fromisoformat(start)
        while d <= min(date.fromisoformat(end), report.attendance_end):
            if d.weekday() < 5 and d not in holidays:
                expected_leave_days.add((emp, d.isoformat()))
            d += timedelta(days=1)
    assert expected_leave_days <= leave_days
    for key, total in used.items():
        if key[1] in ("annual", "sick", "casual"):
            assert balances[key][1] == total
    assert all(entitled >= 0 and u >= 0 for entitled, u in balances.values())


async def test_refuses_when_non_demo_rows_exist_unless_forced(engine, migrated_db, tmp_path):
    with _db(tmp_path) as conn:
        conn.execute("INSERT INTO departments (name, is_demo) VALUES ('Legal', 0)")
        conn.commit()
    with pytest.raises(SeedRefused):
        await _seed(engine)
    with _db(tmp_path) as conn:
        assert _count(conn, "employees") == 0
    await _seed(engine, force=True)
    with _db(tmp_path) as conn:
        assert _count(conn, "employees") == 60
        assert _count(conn, "departments", "is_demo = 0") == 1


async def test_refuses_to_seed_twice_without_reset(engine, migrated_db):
    await _seed(engine)
    with pytest.raises(SeedRefused):
        await _seed(engine)


async def test_reset_removes_only_demo_rows(engine, migrated_db, tmp_path):
    await _seed(engine)
    with _db(tmp_path) as conn:
        conn.execute("INSERT INTO departments (name, is_demo) VALUES ('Legal', 0)")
        conn.execute("INSERT INTO employees (id, full_name, department, job_title,"
                     " employment_status, hire_date, manager_id, is_demo) VALUES"
                     " ('X0001', 'Real Person', 'Legal', 'Counsel', 'active', '2020-01-01',"
                     " NULL, 0)")
        conn.execute("INSERT INTO audit_events (at, actor_user_id, action, channel, target,"
                     " outcome, correlation_id) VALUES ('2026-10-25 08:00:00', 'U0001',"
                     " 'login_success', 'chat', NULL, 'ok', 'c1')")
        conn.execute("INSERT INTO login_failures (user_id, at) VALUES ('U0001',"
                     " '2026-10-25 08:00:00')")
        conn.commit()
    with pytest.raises(SeedRefused):  # non-demo rows exist now
        await _seed(engine, reset=True)
    await _seed(engine, reset=True, force=True)
    with _db(tmp_path) as conn:
        assert _count(conn, "employees") == 61
        assert _count(conn, "employees", "is_demo = 0") == 1
        assert _count(conn, "departments", "is_demo = 0") == 1
        assert _count(conn, "audit_events") == 1  # audit history is never deleted
        assert _count(conn, "users") == 3


async def test_refuses_when_db_not_at_head(engine):
    with pytest.raises(SeedRefused) as exc:
        await _seed(engine)
    assert "alembic upgrade head" in str(exc.value)
