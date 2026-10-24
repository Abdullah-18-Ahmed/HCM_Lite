"""Service result models (data-model.md §4–5).

``ToolResult[T]`` is the envelope returned by services, agent tools and the FastAPI data
endpoints. ``Decimal`` amounts serialize to JSON as 2-dp strings (``Money``).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from hcm_lite.models.domain import (
    EmploymentStatus,
    LeaveStatus,
    LeaveType,
    Role,
    ScopeKind,
)

_CENT = Decimal("0.01")


def _two_dp(value: Decimal) -> str:
    return str(value.quantize(_CENT, rounding=ROUND_HALF_UP))


Money = Annotated[Decimal, PlainSerializer(_two_dp, return_type=str, when_used="json")]

T = TypeVar("T")

ErrorCode = Literal["access_denied", "not_found", "no_data", "invalid_input", "source_unavailable"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- envelope


class ToolError(_Model):
    code: ErrorCode
    message: str


class ToolResult(_Model, Generic[T]):
    ok: bool
    data: T | None = None
    error: ToolError | None = None
    source: str | None = None  # e.g. "hr-db:attendance"
    period: str | None = None
    scope: ScopeKind | None = None
    is_demo: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> ToolResult[T]:
        if self.ok and (self.error is not None or self.data is None):
            raise ValueError("an ok result has data and no error")
        if not self.ok and self.error is None:
            raise ValueError("a failed result has an error")
        return self

    @classmethod
    def success(
        cls,
        data: T,
        *,
        source: str | None = None,
        period: str | None = None,
        scope: ScopeKind | None = None,
        is_demo: bool = False,
    ) -> ToolResult[T]:
        return cls(ok=True, data=data, source=source, period=period, scope=scope,
                   is_demo=is_demo)

    @classmethod
    def failure(
        cls,
        code: ErrorCode,
        message: str,
        *,
        source: str | None = None,
        period: str | None = None,
        scope: ScopeKind | None = None,
        is_demo: bool = False,
    ) -> ToolResult[T]:
        return cls(ok=False, error=ToolError(code=code, message=message), source=source,
                   period=period, scope=scope, is_demo=is_demo)


# --------------------------------------------------------------------------- payloads


class ProfileResult(_Model):
    employee_id: str
    full_name: str
    department: str
    job_title: str
    manager_name: str | None
    hire_date: date


class LeaveRequestItem(_Model):
    reference: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    working_days: int
    status: LeaveStatus
    created_at: datetime


class LeaveRequestList(_Model):
    count: int
    requests: list[LeaveRequestItem]  # newest first


class HeadcountResult(_Model):
    scope: ScopeKind
    total_active: int
    by_department: dict[str, int]
    as_of: date


class PeriodRange(_Model):
    start_date: date
    end_date: date
    label: str


class DepartmentAttendance(_Model):
    department: str
    records: int
    present: int
    remote: int
    absent: int
    on_leave: int
    late: int
    attendance_rate: float  # %, 1 dp


class AttendanceSummary(_Model):
    period: PeriodRange
    working_days: int
    records: int
    present: int
    remote: int
    absent: int
    on_leave: int
    late: int
    attendance_rate: float  # %, 1 dp
    by_department: list[DepartmentAttendance]


class LateEntry(_Model):
    employee_id: str
    full_name: str
    department: str
    date: date
    check_in: str
    minutes_late: int


class LateComersResult(_Model):
    period: PeriodRange
    count: int
    entries: list[LateEntry] = Field(max_length=50)
    truncated: bool = False


class PendingLeave(_Model):
    reference: str
    employee: str
    start_date: date
    end_date: date
    days: int


class LeaveSummary(_Model):
    period: PeriodRange
    by_status: dict[str, int]
    by_type: dict[str, int]
    total_days_approved: int
    pending: list[PendingLeave] = Field(default_factory=list, max_length=25)  # team/all only


class BalanceEntry(_Model):
    leave_type: LeaveType
    entitled: Money
    used: Money
    pending: Money
    remaining: Money


class LeaveBalanceResult(_Model):
    employee_id: str
    year: int
    as_of: date
    balances: list[BalanceEntry]


class PayrollDepartment(_Model):
    department: str
    headcount_paid: int
    gross_total: Money
    net_total: Money


class PayrollSummary(_Model):
    period: str  # YYYY-MM
    currency: str
    gross_total: Money
    net_total: Money
    headcount_paid: int
    by_department: list[PayrollDepartment]


class EmployeeSummary(_Model):
    employee_id: str
    full_name: str
    department: str
    job_title: str
    employment_status: EmploymentStatus


class EmployeeSearchResult(_Model):
    count: int
    employees: list[EmployeeSummary] = Field(max_length=25)


class Citation(_Model):
    n: int
    document_id: str
    title: str
    section: str
    page: int | None = None
    source_path: str

    @property
    def label(self) -> str:
        text = f"[{self.n}] {self.title} — {self.section}"
        return f"{text}, p. {self.page}" if self.page is not None else text


class PolicyChunk(_Model):
    n: int
    text: str  # wrapped as untrusted
    citation: Citation


class PolicySearchResult(_Model):
    found: bool
    chunks: list[PolicyChunk] = Field(default_factory=list)


class DashboardData(_Model):
    role: Role
    sections: dict[str, ToolResult[Any]]
    withheld: list[str] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- leave draft (§5)


class DraftStatus(StrEnum):
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    READY_FOR_REVIEW = "ready_for_review"
    SUBMITTED = "submitted"


class LeaveDraft(_Model):
    draft_id: str  # uuid4; also the idempotency key
    status: DraftStatus = DraftStatus.INCOMPLETE
    leave_type: LeaveType | None = None
    start_date: date | None = None
    end_date: date | None = None
    reason: str | None = None
    working_days: int | None = None
    missing_fields: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    balance_remaining: Money | None = None
    policy_citations: list[Citation] = Field(default_factory=list)
    submitted_reference: str | None = None
