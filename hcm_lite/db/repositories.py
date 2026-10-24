"""Repositories: all SQL lives here (research D-04, constitution Art. IX.1.4–5).

Each repository wraps one ``AsyncSession`` owned by the caller (the caller commits or rolls
back). Methods take explicit ``employee_ids`` filters (``None`` means "no restriction" and must
be passed deliberately), return domain models from ``hcm_lite.models.domain`` and contain no
authorization logic; services decide who may see what.

Errors: ``IntegrityError`` → ``ValidationError(field, message)`` (except the idempotency-key
path of ``LeaveRepo.insert_idempotent``); ``OperationalError`` and other driver errors →
``DatabaseError``. Writes run inside a SAVEPOINT so a rejected row leaves the session usable.
Messages never contain row values.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Awaitable, Callable, Collection, Iterable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ParamSpec, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, delete, func, insert, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hcm_lite.db.tables import (
    DEMO_TABLES,
    Attendance,
    AuditEvent,
    Base,
    Department,
    Employee,
    Holiday,
    LeaveBalance,
    LeaveRequest,
    LeaveTypeRow,
    LoginFailure,
    PayrollTotal,
    User,
)
from hcm_lite.errors import DatabaseError, ValidationError
from hcm_lite.models.domain import (
    AttendanceRecord,
    AuditEventRecord,
    DepartmentRecord,
    EmployeeRecord,
    EmploymentStatus,
    HolidayRecord,
    LeaveBalanceRecord,
    LeaveRequestRecord,
    LeaveTypeRecord,
    PayrollTotalRecord,
    UserRecord,
)

__all__ = [
    "AdminRepo", "AttendanceRepo", "AuditRepo", "EmployeeRepo", "HolidayRepo", "LeaveRepo",
    "LoginFailureRepo", "PayrollRepo", "UserRepo",
]

P = ParamSpec("P")
R = TypeVar("R")
M = TypeVar("M", bound=BaseModel)

DB_UNAVAILABLE = "The HR database is unavailable"

# --------------------------------------------------------------------------- error mapping

_UNIQUE = re.compile(r"UNIQUE constraint failed: ([\w.]+(?:, [\w.]+)*)")
_NOT_NULL = re.compile(r"NOT NULL constraint failed: [\w]+\.(\w+)")
_CHECK = re.compile(r"CHECK constraint failed: (\w+)")


def _check_field(constraint: str) -> str:
    """``ck_attendance_status`` → ``status``; ``ck_leave_requests_end_after_start`` → ..."""
    for model in Base.metadata.tables.values():
        prefix = f"ck_{model.name}_"
        if constraint.startswith(prefix):
            return constraint.removeprefix(prefix)
    return constraint


def _to_validation_error(exc: IntegrityError) -> ValidationError:
    text = str(exc.orig)
    if m := _UNIQUE.search(text):
        columns = [c.split(".")[-1] for c in m.group(1).split(", ")]
        return ValidationError(",".join(columns), "already exists")
    if m := _NOT_NULL.search(text):
        return ValidationError(m.group(1), "is required")
    if m := _CHECK.search(text):
        return ValidationError(_check_field(m.group(1)), "violates a database constraint")
    if "FOREIGN KEY" in text:
        return ValidationError("reference", "refers to a record that does not exist")
    return ValidationError("record", "violates a database constraint")


def _db_errors(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except IntegrityError as exc:
            raise _to_validation_error(exc) from None
        except DBAPIError:  # OperationalError (locked, missing table, I/O) and other driver errors
            raise DatabaseError(DB_UNAVAILABLE) from None

    return wrapper


# --------------------------------------------------------------------------- helpers


def _values(record: BaseModel, *, drop_none_id: bool = True) -> dict[str, Any]:
    data = {k: (v.value if isinstance(v, Enum) else v) for k, v in record}
    if drop_none_id and data.get("id", 0) is None:
        del data["id"]
    return data


def _to(model: type[M], row: Base) -> M:
    return model.model_validate({c.key: getattr(row, c.key) for c in row.__table__.columns})


def _ids_filter(stmt: Select, column: Any, employee_ids: Collection[str] | None) -> Select:
    if employee_ids is None:
        return stmt
    return stmt.where(column.in_(list(employee_ids)))


class _Repo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _add(self, table: type[Base], record: BaseModel) -> Base:
        row = table(**_values(record))
        async with self._s.begin_nested():
            self._s.add(row)
            await self._s.flush()
        return row

    async def _add_many(self, table: type[Base], records: Iterable[BaseModel]) -> int:
        rows = [_values(r) for r in records]
        if not rows:
            return 0
        async with self._s.begin_nested():
            await self._s.execute(insert(table), rows)
        return len(rows)


# --------------------------------------------------------------------------- users


class UserRepo(_Repo):
    @_db_errors
    async def get(self, user_id: str) -> UserRecord | None:
        row = await self._s.get(User, user_id, populate_existing=True)
        return _to(UserRecord, row) if row else None

    @_db_errors
    async def get_by_username(self, username: str) -> UserRecord | None:
        row = (await self._s.execute(select(User).where(User.username == username))).scalar()
        return _to(UserRecord, row) if row else None

    @_db_errors
    async def insert(self, record: UserRecord) -> UserRecord:
        return _to(UserRecord, await self._add(User, record))

    @_db_errors
    async def set_locked_until(self, user_id: str, until: datetime | None) -> None:
        await self._s.execute(update(User).where(User.id == user_id).values(locked_until=until))

    @_db_errors
    async def next_id(self) -> str:
        ids = (await self._s.execute(select(User.id).where(User.id.like("U%")))).scalars()
        numbers = [int(i[1:]) for i in ids if i[1:].isdigit()]
        return f"U{(max(numbers, default=0) + 1):04d}"


class LoginFailureRepo(_Repo):
    @_db_errors
    async def add(self, user_id: str, at: datetime) -> None:
        async with self._s.begin_nested():
            await self._s.execute(insert(LoginFailure).values(user_id=user_id, at=at))

    @_db_errors
    async def count_since(self, user_id: str, since: datetime) -> int:
        stmt = select(func.count()).where(LoginFailure.user_id == user_id,
                                          LoginFailure.at >= since)
        return (await self._s.execute(stmt)).scalar_one()

    @_db_errors
    async def clear(self, user_id: str) -> None:
        await self._s.execute(delete(LoginFailure).where(LoginFailure.user_id == user_id))


# --------------------------------------------------------------------------- employees


class EmployeeRepo(_Repo):
    @_db_errors
    async def insert_departments(self, records: Iterable[DepartmentRecord]) -> int:
        return await self._add_many(Department, records)

    @_db_errors
    async def list_departments(self) -> list[DepartmentRecord]:
        rows = (await self._s.execute(select(Department).order_by(Department.name))).scalars()
        return [_to(DepartmentRecord, r) for r in rows]

    @_db_errors
    async def insert(self, record: EmployeeRecord) -> EmployeeRecord:
        return _to(EmployeeRecord, await self._add(Employee, record))

    @_db_errors
    async def insert_many(self, records: Iterable[EmployeeRecord]) -> int:
        return await self._add_many(Employee, records)

    @_db_errors
    async def get(self, employee_id: str) -> EmployeeRecord | None:
        row = await self._s.get(Employee, employee_id, populate_existing=True)
        return _to(EmployeeRecord, row) if row else None

    @_db_errors
    async def team_of(self, manager_id: str, *, active_only: bool = False) -> list[EmployeeRecord]:
        """Direct reports of ``manager_id`` (not the manager themself)."""
        stmt = select(Employee).where(Employee.manager_id == manager_id).order_by(Employee.id)
        if active_only:
            stmt = stmt.where(Employee.employment_status == EmploymentStatus.ACTIVE.value)
        return [_to(EmployeeRecord, r) for r in (await self._s.execute(stmt)).scalars()]

    @_db_errors
    async def list(
        self, *, employee_ids: Collection[str] | None, department: str | None = None,
        status: EmploymentStatus | None = None,
    ) -> list[EmployeeRecord]:
        stmt = _ids_filter(select(Employee), Employee.id, employee_ids).order_by(Employee.id)
        if department is not None:
            stmt = stmt.where(Employee.department == department)
        if status is not None:
            stmt = stmt.where(Employee.employment_status == EmploymentStatus(status).value)
        return [_to(EmployeeRecord, r) for r in (await self._s.execute(stmt)).scalars()]

    @_db_errors
    async def search(
        self, *, employee_ids: Collection[str] | None, name: str | None = None,
        department: str | None = None, job_title: str | None = None,
        status: EmploymentStatus | None = None, limit: int = 25,
    ) -> list[EmployeeRecord]:
        stmt = _ids_filter(select(Employee), Employee.id, employee_ids)
        if name:
            stmt = stmt.where(Employee.full_name.collate("NOCASE").contains(name,
                                                                            autoescape=True))
        if department is not None:
            stmt = stmt.where(Employee.department == department)
        if job_title:
            stmt = stmt.where(Employee.job_title.collate("NOCASE").contains(job_title,
                                                                            autoescape=True))
        if status is not None:
            stmt = stmt.where(Employee.employment_status == EmploymentStatus(status).value)
        stmt = stmt.order_by(Employee.full_name, Employee.id).limit(limit)
        return [_to(EmployeeRecord, r) for r in (await self._s.execute(stmt)).scalars()]

    @_db_errors
    async def headcount_by_department(
        self, *, employee_ids: Collection[str] | None, department: str | None = None,
    ) -> dict[str, int]:
        """Active employees per department (``COUNT ... GROUP BY``)."""
        stmt = select(Employee.department, func.count()).where(
            Employee.employment_status == EmploymentStatus.ACTIVE.value
        )
        stmt = _ids_filter(stmt, Employee.id, employee_ids)
        if department is not None:
            stmt = stmt.where(Employee.department == department)
        stmt = stmt.group_by(Employee.department)
        return {d: n for d, n in (await self._s.execute(stmt)).all()}


# --------------------------------------------------------------------------- attendance


class AttendanceRepo(_Repo):
    @_db_errors
    async def insert(self, record: AttendanceRecord) -> AttendanceRecord:
        return _to(AttendanceRecord, await self._add(Attendance, record))

    @_db_errors
    async def insert_many(self, records: Iterable[AttendanceRecord]) -> int:
        return await self._add_many(Attendance, records)

    def _range(self, stmt: Select, employee_ids: Collection[str] | None, start: date,
               end: date, department: str | None) -> Select:
        stmt = _ids_filter(stmt, Attendance.employee_id, employee_ids)
        stmt = stmt.where(Attendance.date >= start, Attendance.date <= end)
        if department is not None:
            stmt = stmt.join(Employee, Employee.id == Attendance.employee_id).where(
                Employee.department == department
            )
        return stmt

    @_db_errors
    async def list(
        self, *, employee_ids: Collection[str] | None, start: date, end: date,
        department: str | None = None,
    ) -> list[AttendanceRecord]:
        stmt = self._range(select(Attendance), employee_ids, start, end, department)
        stmt = stmt.order_by(Attendance.date, Attendance.employee_id)
        return [_to(AttendanceRecord, r) for r in (await self._s.execute(stmt)).scalars()]

    @_db_errors
    async def count_by_status(
        self, *, employee_ids: Collection[str] | None, start: date, end: date,
        department: str | None = None,
    ) -> dict[str, int]:
        stmt = self._range(select(Attendance.status, func.count()), employee_ids, start, end,
                           department).group_by(Attendance.status)
        return {s: n for s, n in (await self._s.execute(stmt)).all()}


# --------------------------------------------------------------------------- leave


class LeaveRepo(_Repo):
    @_db_errors
    async def insert_leave_types(self, records: Iterable[LeaveTypeRecord]) -> int:
        return await self._add_many(LeaveTypeRow, records)

    @_db_errors
    async def list_leave_types(self) -> list[LeaveTypeRecord]:
        rows = (await self._s.execute(select(LeaveTypeRow).order_by(LeaveTypeRow.id))).scalars()
        return [_to(LeaveTypeRecord, r) for r in rows]

    @_db_errors
    async def insert_balances(self, records: Iterable[LeaveBalanceRecord]) -> int:
        return await self._add_many(LeaveBalance, records)

    @_db_errors
    async def balances_for(self, employee_id: str, year: int) -> list[LeaveBalanceRecord]:
        stmt = select(LeaveBalance).where(LeaveBalance.employee_id == employee_id,
                                          LeaveBalance.year == year)
        stmt = stmt.order_by(LeaveBalance.leave_type)
        return [_to(LeaveBalanceRecord, r) for r in (await self._s.execute(stmt)).scalars()]

    @_db_errors
    async def insert(self, record: LeaveRequestRecord) -> LeaveRequestRecord:
        return _to(LeaveRequestRecord, await self._add(LeaveRequest, record))

    @_db_errors
    async def insert_many(self, records: Iterable[LeaveRequestRecord]) -> int:
        return await self._add_many(LeaveRequest, records)

    @_db_errors
    async def insert_idempotent(
        self, record: LeaveRequestRecord,
    ) -> tuple[LeaveRequestRecord, bool]:
        """Insert once per ``idempotency_key``: ``(new, True)`` or ``(existing, False)``.

        Only a violation of the ``idempotency_key`` UNIQUE constraint is treated as "already
        submitted"; every other integrity error maps to ``ValidationError``.
        """
        if record.idempotency_key is None:
            raise ValidationError("idempotency_key", "is required")
        try:
            row = await self._add(LeaveRequest, record)
        except IntegrityError as exc:
            match = _UNIQUE.search(str(exc.orig))
            if not match or match.group(1) != "leave_requests.idempotency_key":
                raise
            existing = await self._by_idempotency_key(record.idempotency_key)
            if existing is None:  # pragma: no cover - the UNIQUE violation implies a row
                raise
            return existing, False
        return _to(LeaveRequestRecord, row), True

    async def _by_idempotency_key(self, key: str) -> LeaveRequestRecord | None:
        stmt = select(LeaveRequest).where(LeaveRequest.idempotency_key == key)
        row = (await self._s.execute(stmt)).scalar()
        return _to(LeaveRequestRecord, row) if row else None

    @_db_errors
    async def get(self, request_id: str) -> LeaveRequestRecord | None:
        row = await self._s.get(LeaveRequest, request_id, populate_existing=True)
        return _to(LeaveRequestRecord, row) if row else None

    @_db_errors
    async def get_by_idempotency_key(self, key: str) -> LeaveRequestRecord | None:
        return await self._by_idempotency_key(key)

    def _filter(self, stmt: Select, employee_ids: Collection[str] | None, start: date | None,
                end: date | None, statuses: Collection[str] | None) -> Select:
        stmt = _ids_filter(stmt, LeaveRequest.employee_id, employee_ids)
        if start is not None:  # overlaps [start, end]
            stmt = stmt.where(LeaveRequest.end_date >= start)
        if end is not None:
            stmt = stmt.where(LeaveRequest.start_date <= end)
        if statuses is not None:
            stmt = stmt.where(LeaveRequest.status.in_([str(s) for s in statuses]))
        return stmt

    @_db_errors
    async def list_for_employees(
        self, *, employee_ids: Collection[str] | None, start: date | None = None,
        end: date | None = None, statuses: Collection[str] | None = None,
        limit: int | None = None,
    ) -> list[LeaveRequestRecord]:
        """Requests overlapping ``[start, end]`` (when given), newest first."""
        stmt = self._filter(select(LeaveRequest), employee_ids, start, end, statuses)
        stmt = stmt.order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_to(LeaveRequestRecord, r) for r in (await self._s.execute(stmt)).scalars()]

    @_db_errors
    async def count_by_status(
        self, *, employee_ids: Collection[str] | None, start: date, end: date,
    ) -> dict[str, int]:
        stmt = self._filter(select(LeaveRequest.status, func.count()), employee_ids, start,
                            end, None).group_by(LeaveRequest.status)
        return {s: n for s, n in (await self._s.execute(stmt)).all()}

    @_db_errors
    async def sum_days_by_type(
        self, *, employee_ids: Collection[str] | None, start: date, end: date,
        statuses: Collection[str],
    ) -> dict[str, int]:
        """``SUM(working_days) GROUP BY leave_type`` for requests overlapping the range."""
        stmt = self._filter(
            select(LeaveRequest.leave_type, func.sum(LeaveRequest.working_days)),
            employee_ids, start, end, statuses,
        ).group_by(LeaveRequest.leave_type)
        return {t: int(n) for t, n in (await self._s.execute(stmt)).all()}


# --------------------------------------------------------------------------- payroll, holidays


class PayrollRepo(_Repo):
    @_db_errors
    async def insert_many(self, records: Iterable[PayrollTotalRecord]) -> int:
        return await self._add_many(PayrollTotal, records)

    @_db_errors
    async def by_period(self, period: str, *, department: str | None = None,
                        ) -> list[PayrollTotalRecord]:
        stmt = select(PayrollTotal).where(PayrollTotal.period == period)
        if department is not None:
            stmt = stmt.where(PayrollTotal.department == department)
        stmt = stmt.order_by(PayrollTotal.department)
        return [_to(PayrollTotalRecord, r) for r in (await self._s.execute(stmt)).scalars()]

    @_db_errors
    async def totals_for_period(self, period: str, *, department: str | None = None,
                                ) -> tuple[int, Decimal, Decimal]:
        """``(SUM headcount_paid, SUM gross_total, SUM net_total)`` for the period."""
        stmt = select(
            func.coalesce(func.sum(PayrollTotal.headcount_paid), 0),
            func.coalesce(func.sum(PayrollTotal.gross_total), 0),
            func.coalesce(func.sum(PayrollTotal.net_total), 0),
        ).where(PayrollTotal.period == period)
        if department is not None:
            stmt = stmt.where(PayrollTotal.department == department)
        headcount, gross, net = (await self._s.execute(stmt)).one()
        cents = Decimal("0.01")
        return int(headcount), Decimal(str(gross)).quantize(cents), Decimal(
            str(net)).quantize(cents)


class HolidayRepo(_Repo):
    @_db_errors
    async def insert_many(self, records: Iterable[HolidayRecord]) -> int:
        return await self._add_many(Holiday, records)

    @_db_errors
    async def between(self, start: date, end: date) -> list[HolidayRecord]:
        stmt = select(Holiday).where(Holiday.date >= start, Holiday.date <= end)
        stmt = stmt.order_by(Holiday.date)
        return [_to(HolidayRecord, r) for r in (await self._s.execute(stmt)).scalars()]


# --------------------------------------------------------------------------- audit


class AuditRepo(_Repo):
    @_db_errors
    async def insert(self, record: AuditEventRecord) -> AuditEventRecord:
        return _to(AuditEventRecord, await self._add(AuditEvent, record))

    @_db_errors
    async def list_recent(self, *, limit: int = 50, action: str | None = None,
                          ) -> list[AuditEventRecord]:
        stmt = select(AuditEvent)
        if action is not None:
            stmt = stmt.where(AuditEvent.action == str(action))
        stmt = stmt.order_by(AuditEvent.at.desc(), AuditEvent.id.desc()).limit(limit)
        return [_to(AuditEventRecord, r) for r in (await self._s.execute(stmt)).scalars()]


# --------------------------------------------------------------------------- maintenance


class AdminRepo(_Repo):
    """Row counts and demo-data maintenance for the ``status`` / ``seed`` commands."""

    @_db_errors
    async def row_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for name in sorted(Base.metadata.tables):
            table = Base.metadata.tables[name]
            counts[name] = (await self._s.execute(select(func.count()).select_from(table))
                            ).scalar_one()
        return counts

    async def _count_demo(self, demo: bool) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in DEMO_TABLES:
            stmt = select(func.count()).select_from(table).where(table.is_demo.is_(demo))
            counts[table.__tablename__] = (await self._s.execute(stmt)).scalar_one()
        return counts

    @_db_errors
    async def non_demo_counts(self) -> dict[str, int]:
        """Tables holding rows with ``is_demo = 0`` (only those with at least one)."""
        return {t: n for t, n in (await self._count_demo(False)).items() if n}

    @_db_errors
    async def demo_counts(self) -> dict[str, int]:
        return await self._count_demo(True)

    @_db_errors
    async def delete_demo_rows(self) -> None:
        """Delete every ``is_demo = 1`` row (children first). Audit history is kept."""
        demo_users = select(User.id).where(User.is_demo.is_(True))
        async with self._s.begin_nested():
            await self._s.execute(
                delete(LoginFailure).where(LoginFailure.user_id.in_(demo_users))
            )
            for table in reversed(DEMO_TABLES):
                await self._s.execute(delete(table).where(table.is_demo.is_(True)))
