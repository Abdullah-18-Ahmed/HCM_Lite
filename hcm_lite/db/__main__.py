"""``python -m hcm_lite.db status | seed [--force] [--reset] | create-user`` (contracts/cli.md).

Exit codes: ``status`` 0, 1 = DB unreadable; ``seed`` 0 ok, 2 refused, 1 error; ``create-user``
0 / 1. Passwords are read with ``getpass`` (never an argument) and never printed, except the
generated demo passwords, which ``seed`` prints once.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

import pydantic

from hcm_lite.config import Settings, get_settings
from hcm_lite.db.engine import (
    OUT_OF_DATE_MESSAGE,
    assert_at_head,
    create_engine,
    current_revision,
    head_revision,
    session_factory,
)
from hcm_lite.db.repositories import AdminRepo, EmployeeRepo, UserRepo
from hcm_lite.db.seed import SeedRefused, run_seed
from hcm_lite.errors import ConfigurationError, DatabaseError, ValidationError
from hcm_lite.models.domain import Role, UserRecord
from hcm_lite.services.passwords import hash_password

MIN_PASSWORD_LENGTH = 8
_seed_hasher = hash_password  # replaced by a fast hasher in tests


def _err(message: str) -> None:
    print(message, file=sys.stderr)


async def _status(settings: Settings) -> int:
    engine = create_engine(settings)
    try:
        current, head = await current_revision(engine), head_revision()
        at_head = current == head
        state = "at head" if at_head else "NOT at head — run alembic upgrade head"
        print(f"Revision: current {current or 'none'}, head {head} ({state})")
        if current is None:
            return 0
        async with session_factory(engine)() as session:
            counts = await AdminRepo(session).row_counts()
        print("Rows:")
        for table, count in counts.items():
            print(f"  {table:<16} {count}")
        return 0
    except DatabaseError as exc:
        _err(f"Error: {exc.message}")
        return 1
    finally:
        await engine.dispose()


async def _seed(settings: Settings, force: bool, reset: bool) -> int:
    engine = create_engine(settings)
    try:
        today = datetime.now(settings.tz).date()
        report = await run_seed(engine, today=today, force=force, reset=reset,
                                hasher=_seed_hasher)
    except SeedRefused as exc:
        _err(f"Refused: {exc.message}")
        return 2
    except (DatabaseError, ValidationError) as exc:
        _err(f"Error: {exc.message}")
        return 1
    finally:
        await engine.dispose()
    rows = ", ".join(f"{t} {n}" for t, n in report.counts.items())
    print(f"DEMO data created (fictional, is_demo = 1). Rows created: {rows}.")
    print(f"Attendance runs through {report.attendance_end.isoformat()}.")
    print("DEMO credentials (generated now, shown only once; for demonstration only):")
    for cred in report.credentials:
        print(f"  {cred.username:<10} role={cred.role.value:<9} employee={cred.employee_id}"
              f"  password: {cred.password}")
    return 0


async def _create_user(settings: Settings, username: str, role: str, employee_id: str) -> int:
    try:
        role_value = Role(role)
    except ValueError:
        _err(f"Error: --role must be one of {', '.join(r.value for r in Role)}")
        return 1
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        _err("Error: the passwords do not match")
        return 1
    if len(password) < MIN_PASSWORD_LENGTH:
        _err(f"Error: the password must be at least {MIN_PASSWORD_LENGTH} characters")
        return 1
    engine = create_engine(settings)
    try:
        await assert_at_head(engine)
        async with session_factory(engine)() as session, session.begin():
            if await EmployeeRepo(session).get(employee_id) is None:
                _err("Error: --employee-id does not match an employee")
                return 1
            users = UserRepo(session)
            record = UserRecord(
                id=await users.next_id(), username=username,
                password_hash=hash_password(password), role=role_value,
                employee_id=employee_id, active=True, is_demo=False,
                created_at=datetime.now(UTC),
            )
            created = await users.insert(record)
    except ConfigurationError:
        _err(f"Error: {OUT_OF_DATE_MESSAGE}")
        return 1
    except ValidationError as exc:
        _err(f"Error: {exc.field} {exc.message}")
        return 1
    except pydantic.ValidationError as exc:
        fields = ", ".join(str(e["loc"][0]) for e in exc.errors(include_input=False))
        _err(f"Error: invalid {fields}")
        return 1
    except DatabaseError as exc:
        _err(f"Error: {exc.message}")
        return 1
    finally:
        await engine.dispose()
    print(f"Created user {created.username} ({created.id}, role {created.role.value}).")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hcm_lite.db",
                                     description="HCM Lite database tools")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="current vs head revision and row counts")
    seed = sub.add_parser("seed", help="create labelled demo data and demo accounts")
    seed.add_argument("--force", action="store_true", help="seed even if non-demo rows exist")
    seed.add_argument("--reset", action="store_true", help="delete demo rows first")
    create = sub.add_parser("create-user", help="create a non-demo account (password prompt)")
    create.add_argument("--username", required=True)
    create.add_argument("--role", required=True)
    create.add_argument("--employee-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        _err(exc.message)
        return 1
    if args.command == "status":
        return asyncio.run(_status(settings))
    if args.command == "seed":
        return asyncio.run(_seed(settings, args.force, args.reset))
    return asyncio.run(_create_user(settings, args.username, args.role, args.employee_id))


if __name__ == "__main__":
    sys.exit(main())
