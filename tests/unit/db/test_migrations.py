"""T013 (+ T026 engine checks): Alembic migrations on a fresh temp SQLite DB per test."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text

from hcm_lite.db.engine import alembic_config, assert_at_head, create_engine, head_revision
from hcm_lite.errors import ConfigurationError

from tests.conftest import run_alembic

TABLES = {
    "users", "login_failures", "departments", "employees", "attendance", "leave_types",
    "leave_balances", "leave_requests", "payroll_totals", "holidays", "audit_events",
}

# table -> {(from_column, referenced_table, referenced_column)}
FOREIGN_KEYS = {
    "users": {("employee_id", "employees", "id")},
    "login_failures": {("user_id", "users", "id")},
    "employees": {("department", "departments", "name"), ("manager_id", "employees", "id")},
    "attendance": {("employee_id", "employees", "id")},
    "leave_balances": {("employee_id", "employees", "id"), ("leave_type", "leave_types", "id")},
    "leave_requests": {
        ("employee_id", "employees", "id"), ("leave_type", "leave_types", "id"),
        ("created_by", "users", "id"),
    },
    "payroll_totals": {("department", "departments", "name")},
}

# table -> {(unique?, (columns...))}; a COLLATE index reports its column in PRAGMA index_info
INDEXES = {
    "users": {(True, ("username",)), (True, ("employee_id",)), (True, ("email",))},
    "login_failures": {(False, ("user_id", "at"))},
    "employees": {
        (False, ("department", "employment_status")), (False, ("manager_id",)),
        (False, ("full_name",)),  # (full_name COLLATE NOCASE), checked below
    },
    "attendance": {(True, ("employee_id", "date")), (False, ("date",))},
    "leave_balances": {(True, ("employee_id", "leave_type", "year"))},
    "leave_requests": {
        (True, ("idempotency_key",)), (False, ("employee_id", "start_date")),
        (False, ("status",)),
    },
    "payroll_totals": {(True, ("period", "department"))},
    "audit_events": {(False, ("at",))},
}

# table -> CHECK constraint names that must appear in the CREATE TABLE statement
CHECKS = {
    "users": {"ck_users_username_length", "ck_users_role"},
    "employees": {"ck_employees_employment_status"},
    "attendance": {"ck_attendance_status", "ck_attendance_check_in_required"},
    "leave_types": {"ck_leave_types_id"},
    "leave_balances": {"ck_leave_balances_entitled_non_negative",
                       "ck_leave_balances_used_non_negative"},
    "leave_requests": {
        "ck_leave_requests_end_after_start", "ck_leave_requests_working_days_positive",
        "ck_leave_requests_status", "ck_leave_requests_source",
    },
    "payroll_totals": {
        "ck_payroll_totals_headcount_non_negative", "ck_payroll_totals_gross_non_negative",
        "ck_payroll_totals_net_non_negative",
    },
    "audit_events": {"ck_audit_events_action", "ck_audit_events_channel",
                     "ck_audit_events_outcome"},
}

NULLABLE = {  # every other column must be NOT NULL (Art. IX.1.2)
    ("users", "locked_until"), ("employees", "manager_id"), ("attendance", "check_in"),
    ("leave_requests", "idempotency_key"), ("audit_events", "actor_user_id"),
    ("audit_events", "target"),
}


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "hcm_test.db"


def _connect(tmp_path: Path):
    return closing(sqlite3.connect(_db_path(tmp_path)))


def _tables(tmp_path: Path) -> set[str]:
    with _connect(tmp_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {r[0] for r in rows}


def test_upgrade_head_creates_every_table(migrated_db, tmp_path):
    assert _tables(tmp_path) == TABLES | {"alembic_version"}
    with _connect(tmp_path) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    assert version == [(head_revision(),)]
    assert head_revision() == "0002"


def test_foreign_keys_declared(migrated_db, tmp_path):
    with _connect(tmp_path) as conn:
        for table in TABLES:
            rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            found = {(r[3], r[2], r[4]) for r in rows}
            assert found == FOREIGN_KEYS.get(table, set()), table


def test_unique_and_secondary_indexes_declared(migrated_db, tmp_path):
    with _connect(tmp_path) as conn:
        for table in TABLES:
            found = set()
            for _, name, unique, origin, _partial in conn.execute(
                f"PRAGMA index_list({table})"
            ).fetchall():
                if origin == "pk":
                    continue
                cols = tuple(r[2] for r in conn.execute(f"PRAGMA index_info('{name}')"))
                found.add((bool(unique), cols))
            assert found == INDEXES.get(table, set()), table
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND name='ix_employees_full_name_nocase'"
        ).fetchone()[0]
    assert "COLLATE NOCASE" in sql.upper()


def test_check_constraints_declared(migrated_db, tmp_path):
    with _connect(tmp_path) as conn:
        for table, names in CHECKS.items():
            sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()[0]
            for name in names:
                assert f"CONSTRAINT {name} CHECK" in sql, (table, name)


def test_not_null_everywhere_except_documented_columns(migrated_db, tmp_path):
    with _connect(tmp_path) as conn:
        for table in TABLES:
            for _cid, col, _type, notnull, _default, pk in conn.execute(
                f"PRAGMA table_info({table})"
            ).fetchall():
                if (table, col) in NULLABLE:
                    assert not notnull, (table, col)
                else:
                    assert notnull or pk, (table, col)


def test_downgrade_base_then_upgrade_head(migrated_db, alembic_cfg, tmp_path):
    run_alembic(command.downgrade, alembic_cfg, "base")
    assert _tables(tmp_path) == {"alembic_version"}
    run_alembic(command.upgrade, alembic_cfg, "head")
    assert _tables(tmp_path) == TABLES | {"alembic_version"}


def _user_columns(tmp_path: Path) -> set[str]:
    with _connect(tmp_path) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}


def test_0002_down_up_cycle_adds_email_and_new_values(migrated_db, alembic_cfg, tmp_path):
    assert "email" in _user_columns(tmp_path)
    run_alembic(command.downgrade, alembic_cfg, "0001")
    assert "email" not in _user_columns(tmp_path)
    run_alembic(command.upgrade, alembic_cfg, "head")
    assert "email" in _user_columns(tmp_path)

    with _connect(tmp_path) as conn:
        conn.execute("INSERT INTO departments (name, is_demo) VALUES ('Administration', 0)")
        conn.execute(
            "INSERT INTO employees (id, full_name, department, job_title, employment_status,"
            " hire_date, is_demo) VALUES ('A0001', 'Admin', 'Administration', 'Administrator',"
            " 'active', '2026-01-01', 0)"
        )
        conn.execute(
            "INSERT INTO users (id, username, email, password_hash, role, employee_id, active,"
            " is_demo, created_at) VALUES ('U9001', 'root', 'root@demo.hcm', 'h', 'admin',"
            " 'A0001', 1, 0, '2026-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO audit_events (at, action, channel, outcome, correlation_id)"
            " VALUES ('2026-01-01 00:00:00', 'user_created', 'api', 'ok', 'cid')"
        )
        conn.commit()
        assert conn.execute("SELECT role FROM users WHERE id='U9001'").fetchone()[0] == "admin"
        assert conn.execute("SELECT action FROM audit_events").fetchone()[0] == "user_created"


def test_second_upgrade_is_a_noop(migrated_db, alembic_cfg, tmp_path):
    with _connect(tmp_path) as conn:
        conn.execute("INSERT INTO departments (name, is_demo) VALUES ('Keep', 0)")
        conn.commit()
    run_alembic(command.upgrade, alembic_cfg, "head")
    with _connect(tmp_path) as conn:
        assert conn.execute("SELECT name FROM departments").fetchall() == [("Keep",)]
        assert conn.execute("SELECT version_num FROM alembic_version").fetchall() == [("0002",)]


def test_alembic_check_reports_no_drift(migrated_db, alembic_cfg):
    run_alembic(command.check, alembic_cfg)  # raises AutogenerateDiffsDetected on drift


def test_alembic_config_has_no_url_in_ini():
    ini = Path(__file__).resolve().parents[3] / "alembic.ini"
    content = ini.read_text(encoding="utf-8")
    assert "script_location" in content
    assert "sqlalchemy.url" not in content
    assert alembic_config("sqlite+aiosqlite:///x.db").get_main_option("sqlalchemy.url") is None


# --------------------------------------------------------------------------- engine (T026)


async def test_engine_sets_pragmas(engine, migrated_db):
    async with engine.connect() as conn:
        assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await conn.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
        assert (await conn.execute(text("PRAGMA busy_timeout"))).scalar() == 5000


async def test_assert_at_head_passes_on_migrated_db(engine, migrated_db):
    await assert_at_head(engine)


async def test_assert_at_head_fails_on_unmigrated_db(engine):
    with pytest.raises(ConfigurationError) as exc:
        await assert_at_head(engine)
    assert "run alembic upgrade head" in str(exc.value)


async def test_assert_at_head_fails_after_downgrade(engine, migrated_db, alembic_cfg):
    run_alembic(command.downgrade, alembic_cfg, "base")
    with pytest.raises(ConfigurationError):
        await assert_at_head(engine)


async def test_create_engine_creates_missing_data_folder(settings, tmp_path, monkeypatch):
    target = tmp_path / "nested" / "data" / "hcm.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{target.as_posix()}")
    from hcm_lite.config import load_settings

    eng = create_engine(load_settings(env_file=None))
    try:
        assert target.parent.is_dir()
        async with eng.connect() as conn:
            assert (await conn.execute(text("SELECT 1"))).scalar() == 1
    finally:
        await eng.dispose()
