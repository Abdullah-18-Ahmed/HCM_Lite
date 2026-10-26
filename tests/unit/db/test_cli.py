"""T031: ``python -m hcm_lite.db`` (contracts/cli.md) exit codes and output."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from hcm_lite.config import get_settings
from hcm_lite.db import __main__ as cli
from hcm_lite.services.passwords import hash_password, verify_password


@pytest.fixture
def cli_env(settings, monkeypatch):
    """CLI reads settings via get_settings(); use the temp DB and a fast hasher."""
    get_settings.cache_clear()
    monkeypatch.setattr(cli, "_seed_hasher", lambda p: hash_password(p, iterations=1_000))
    yield
    get_settings.cache_clear()


def _db(tmp_path):
    return closing(sqlite3.connect(tmp_path / "hcm_test.db"))


def test_status_reports_revision_and_counts(cli_env, migrated_db, capsys):
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "0002" in out and "head" in out
    assert "employees" in out


def test_status_unreadable_db_exits_1(cli_env, tmp_path, capsys):
    (tmp_path / "hcm_test.db").write_bytes(b"not a database" * 200)
    assert cli.main(["status"]) == 1


def test_seed_prints_demo_credentials(cli_env, migrated_db, capsys, tmp_path):
    assert cli.main(["seed"]) == 0
    out = capsys.readouterr().out
    assert "DEMO" in out
    with _db(tmp_path) as conn:
        hashes = dict(conn.execute("SELECT username, password_hash FROM users"))
    for username in ("employee", "manager", "hr_admin"):
        line = next(ln for ln in out.splitlines() if ln.strip().startswith(username))
        password = line.split()[-1]
        assert verify_password(password, hashes[username])


def test_seed_refusals_exit_2(cli_env, migrated_db, tmp_path):
    with _db(tmp_path) as conn:
        conn.execute("INSERT INTO departments (name, is_demo) VALUES ('Legal', 0)")
        conn.commit()
    assert cli.main(["seed"]) == 2
    assert cli.main(["seed", "--force"]) == 0
    assert cli.main(["seed", "--force"]) == 2  # demo data already present, no --reset
    assert cli.main(["seed", "--force", "--reset"]) == 0


def test_seed_not_at_head_exits_2(cli_env):
    assert cli.main(["seed"]) == 2


def test_create_user_reads_password_from_prompt(cli_env, migrated_db, tmp_path, monkeypatch):
    assert cli.main(["seed"]) == 0
    prompts = iter(["s3cret-passw0rd", "s3cret-passw0rd"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(prompts))
    rc = cli.main(["create-user", "--username", "jdoe", "--role", "manager",
                   "--employee-id", "E1010"])
    assert rc == 0
    with _db(tmp_path) as conn:
        row = conn.execute(
            "SELECT id, role, employee_id, is_demo, password_hash FROM users WHERE username='jdoe'"
        ).fetchone()
    assert row[:4] == ("U0004", "manager", "E1010", 0)
    assert verify_password("s3cret-passw0rd", row[4])


@pytest.mark.parametrize(
    ("args", "passwords"),
    [
        (["--username", "jdoe", "--role", "boss", "--employee-id", "E1010"], ["pw123456"] * 2),
        (["--username", "jdoe", "--role", "employee", "--employee-id", "Z9999"],
         ["pw123456"] * 2),
        (["--username", "employee", "--role", "employee", "--employee-id", "E1010"],
         ["pw123456"] * 2),
        (["--username", "jdoe", "--role", "employee", "--employee-id", "E1010"],
         ["pw123456", "different"]),
        (["--username", "jdoe", "--role", "employee", "--employee-id", "E1010"], ["short"] * 2),
    ],
)
def test_create_user_errors_exit_1(cli_env, migrated_db, monkeypatch, args, passwords, capsys):
    assert cli.main(["seed"]) == 0
    capsys.readouterr()
    prompts = iter(passwords)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(prompts))
    assert cli.main(["create-user", *args]) == 1
    out = capsys.readouterr()
    for pw in passwords:
        assert pw not in out.out + out.err


def test_create_user_has_no_password_argument():
    with pytest.raises(SystemExit):
        cli.main(["create-user", "--username", "x", "--role", "employee", "--employee-id",
                  "E1", "--password", "p"])
