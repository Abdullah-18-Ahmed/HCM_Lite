"""SQLAlchemy 2 ORM tables (data-model.md §1). The schema is created only by Alembic.

Every table declares its PK, NOT NULL, FK, UNIQUE and CHECK constraints so invalid data is
rejected by SQLite itself (constitution Art. IX.1.2). Constraint names follow
``NAMING_CONVENTION`` so error messages and migrations are stable.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    TypeDecorator,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from hcm_lite.models.domain import (
    AttendanceStatus,
    AuditAction,
    AuditOutcome,
    Channel,
    EmploymentStatus,
    LeaveSource,
    LeaveStatus,
    LeaveType,
    Role,
)

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


#: Expression indexes are created by hand in the migration; SQLite cannot reflect them, so
#: autogenerate / ``alembic check`` must not compare them (migrations/env.py ``include_object``).
HAND_MANAGED_INDEXES = frozenset({"ix_employees_full_name_nocase"})


def _in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


class UTCDateTime(TypeDecorator[dt.datetime]):
    """``DATETIME`` stored as naive UTC; returned as an aware UTC ``datetime``."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: dt.datetime | None, dialect) -> dt.datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(dt.UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: dt.datetime | None, dialect) -> dt.datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _is_demo(default: bool | None = None) -> Mapped[bool]:
    if default is None:
        return mapped_column(Boolean, nullable=False)
    return mapped_column(Boolean, nullable=False, server_default=text("1" if default else "0"))


class Department(Base):
    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    is_demo: Mapped[bool] = _is_demo(False)


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(_in("employment_status", EmploymentStatus), name="employment_status"),
        Index(None, "department", "employment_status"),
        Index(None, "manager_id"),
        Index("ix_employees_full_name_nocase", text("full_name COLLATE NOCASE")),
    )

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    department: Mapped[str] = mapped_column(
        String(60), ForeignKey("departments.name"), nullable=False
    )
    job_title: Mapped[str] = mapped_column(String(80), nullable=False)
    employment_status: Mapped[str] = mapped_column(String(10), nullable=False)
    hire_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    manager_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("employees.id"), nullable=True
    )
    is_demo: Mapped[bool] = _is_demo()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(username) BETWEEN 3 AND 40", name="username_length"),
        CheckConstraint(_in("role", Role), name="role"),
        UniqueConstraint("username"),
        UniqueConstraint("employee_id"),
        UniqueConstraint("email"),
    )

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    username: Mapped[str] = mapped_column(String(40), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    employee_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("employees.id"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("1"))
    locked_until: Mapped[dt.datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_demo: Mapped[bool] = _is_demo(False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, nullable=False)


class LoginFailure(Base):
    __tablename__ = "login_failures"
    __table_args__ = (Index(None, "user_id", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(10), ForeignKey("users.id"), nullable=False)
    at: Mapped[dt.datetime] = mapped_column(UTCDateTime, nullable=False)


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        CheckConstraint(_in("status", AttendanceStatus), name="status"),
        CheckConstraint(
            "status NOT IN ('present', 'remote') OR check_in IS NOT NULL",
            name="check_in_required",
        ),
        UniqueConstraint("employee_id", "date"),
        Index(None, "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("employees.id"), nullable=False
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    check_in: Mapped[str | None] = mapped_column(String(5), nullable=True)
    scheduled_start: Mapped[str] = mapped_column(String(5), nullable=False)
    is_demo: Mapped[bool] = _is_demo()


class LeaveTypeRow(Base):
    __tablename__ = "leave_types"
    __table_args__ = (CheckConstraint(_in("id", LeaveType), name="id"),)

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    is_demo: Mapped[bool] = _is_demo(False)


class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    __table_args__ = (
        CheckConstraint("entitled >= 0", name="entitled_non_negative"),
        CheckConstraint("used >= 0", name="used_non_negative"),
        UniqueConstraint("employee_id", "leave_type", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("employees.id"), nullable=False
    )
    leave_type: Mapped[str] = mapped_column(
        String(10), ForeignKey("leave_types.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    entitled: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    used: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    as_of: Mapped[dt.date] = mapped_column(Date, nullable=False)
    is_demo: Mapped[bool] = _is_demo(False)


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="end_after_start"),
        CheckConstraint("working_days >= 1", name="working_days_positive"),
        CheckConstraint(_in("status", LeaveStatus), name="status"),
        CheckConstraint(_in("source", LeaveSource), name="source"),
        UniqueConstraint("idempotency_key"),
        Index(None, "employee_id", "start_date"),
        Index(None, "status"),
    )

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    employee_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("employees.id"), nullable=False
    )
    leave_type: Mapped[str] = mapped_column(
        String(10), ForeignKey("leave_types.id"), nullable=False
    )
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    working_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(10), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, nullable=False)
    is_demo: Mapped[bool] = _is_demo()


class PayrollTotal(Base):
    __tablename__ = "payroll_totals"
    __table_args__ = (
        CheckConstraint("headcount_paid >= 0", name="headcount_non_negative"),
        CheckConstraint("gross_total >= 0", name="gross_non_negative"),
        CheckConstraint("net_total >= 0", name="net_non_negative"),
        UniqueConstraint("period", "department"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    department: Mapped[str] = mapped_column(
        String(60), ForeignKey("departments.name"), nullable=False
    )
    headcount_paid: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    net_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    is_demo: Mapped[bool] = _is_demo(False)


class Holiday(Base):
    __tablename__ = "holidays"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_demo: Mapped[bool] = _is_demo(False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(_in("action", AuditAction), name="action"),
        CheckConstraint(_in("channel", Channel), name="channel"),
        CheckConstraint(_in("outcome", AuditOutcome), name="outcome"),
        Index(None, "at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[dt.datetime] = mapped_column(UTCDateTime, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(10), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    target: Mapped[str | None] = mapped_column(String(60), nullable=True)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)


#: Tables that carry an ``is_demo`` flag, in an order safe for inserts (parents first).
DEMO_TABLES: tuple[type[Base], ...] = (
    Department, LeaveTypeRow, Holiday, Employee, User, LeaveBalance, LeaveRequest, Attendance,
    PayrollTotal,
)
