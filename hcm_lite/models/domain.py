"""Domain enums and record models (data-model.md §1–2).

Records mirror the SQLite tables and are what repositories return. ``AuthenticatedUser`` is
always reloaded from the database; nothing else may supply identity or role.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Role(StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    HR_ADMIN = "hr_admin"


class EmploymentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class LeaveType(StrEnum):
    ANNUAL = "annual"
    SICK = "sick"
    CASUAL = "casual"
    UNPAID = "unpaid"
    OTHER = "other"


class LeaveStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LeaveSource(StrEnum):
    ASSISTANT = "assistant"
    API = "api"
    SEED = "seed"


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    REMOTE = "remote"
    ABSENT = "absent"
    LEAVE = "leave"


class AuditAction(StrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    ACCOUNT_LOCKED = "account_locked"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"
    ACCESS_DENIED = "access_denied"
    LEAVE_SUBMITTED = "leave_submitted"


class AuditOutcome(StrEnum):
    OK = "ok"
    DENIED = "denied"
    ERROR = "error"


class Channel(StrEnum):
    CHAT = "chat"
    API = "api"


class AccessScope(StrEnum):
    """Document access classification (data-model.md §3)."""

    ALL_EMPLOYEES = "all_employees"
    MANAGERS = "managers"
    HR_ADMIN = "hr_admin"
    RESTRICTED = "restricted"


ScopeKind = Literal["self", "team", "all"]

# Relative period keywords (contracts/agent-tools.md); "YYYY-MM" is also accepted.
PERIOD_KEYWORDS: tuple[str, ...] = (
    "today", "yesterday", "this_week", "last_week", "this_month", "last_month", "this_quarter",
)
YEAR_MONTH_PATTERN = r"^(19|20)[0-9]{2}-(0[1-9]|1[0-2])$"  # years 1900-2099


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- identity


class AuthenticatedUser(_Frozen):
    user_id: str
    username: str
    role: Role
    employee_id: str
    display_name: str
    department: str


class Scope(_Frozen):
    """Which employees a user may see. ``employee_ids`` is None only for ``all``."""

    kind: ScopeKind
    employee_ids: frozenset[str] | None

    @model_validator(mode="after")
    def _ids_match_kind(self) -> Scope:
        if (self.kind == "all") != (self.employee_ids is None):
            raise ValueError("employee_ids must be None exactly when kind is 'all'")
        return self

    def includes(self, employee_id: str) -> bool:
        return self.employee_ids is None or employee_id in self.employee_ids


class DateRange(_Frozen):
    """An inclusive date range resolved from a period keyword or ISO dates."""

    start: date
    end: date
    label: str

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.end < self.start:
            raise ValueError("end must be on or after start")
        return self

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


# --------------------------------------------------------------------------- records


class UserRecord(_Frozen):
    id: str
    username: str = Field(min_length=3, max_length=40)
    password_hash: str = Field(repr=False)
    role: Role
    employee_id: str
    active: bool = True
    locked_until: datetime | None = None
    is_demo: bool = False
    created_at: datetime


class DepartmentRecord(_Frozen):
    name: str
    is_demo: bool = False


class EmployeeRecord(_Frozen):
    id: str
    full_name: str
    department: str
    job_title: str
    employment_status: EmploymentStatus
    hire_date: date
    manager_id: str | None = None
    is_demo: bool = False


class AttendanceRecord(_Frozen):
    id: int | None = None
    employee_id: str
    date: date
    status: AttendanceStatus
    check_in: str | None = None  # "HH:MM"
    scheduled_start: str  # "HH:MM"
    is_demo: bool = False


class LeaveTypeRecord(_Frozen):
    id: LeaveType
    label: str
    is_demo: bool = False


class LeaveBalanceRecord(_Frozen):
    id: int | None = None
    employee_id: str
    leave_type: LeaveType
    year: int
    entitled: Decimal = Field(ge=0)
    used: Decimal = Field(ge=0)
    as_of: date
    is_demo: bool = False


class LeaveRequestRecord(_Frozen):
    id: str  # reference LR-YYYYMMDD-XXXX
    employee_id: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    working_days: int = Field(ge=1)
    reason: str = Field(max_length=500)
    status: LeaveStatus
    source: LeaveSource
    idempotency_key: str | None = None
    created_by: str
    created_at: datetime
    is_demo: bool = False


class PayrollTotalRecord(_Frozen):
    id: int | None = None
    period: str = Field(pattern=YEAR_MONTH_PATTERN)
    department: str
    headcount_paid: int = Field(ge=0)
    gross_total: Decimal = Field(ge=0)
    net_total: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    is_demo: bool = False


class HolidayRecord(_Frozen):
    date: date
    name: str
    is_demo: bool = False


class AuditEventRecord(_Frozen):
    id: int | None = None
    at: datetime
    actor_user_id: str | None = None
    action: AuditAction
    channel: Channel
    target: str | None = None
    outcome: AuditOutcome
    correlation_id: str
