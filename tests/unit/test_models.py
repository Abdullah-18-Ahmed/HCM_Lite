"""T019, T022, T023: errors, domain models and result envelopes."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pydantic
import pytest

from hcm_lite import errors
from hcm_lite.models.domain import (
    AttendanceStatus,
    AuditAction,
    AuthenticatedUser,
    Channel,
    DateRange,
    LeaveStatus,
    LeaveType,
    Role,
    Scope,
)
from hcm_lite.models.results import (
    BalanceEntry,
    Citation,
    DraftStatus,
    HeadcountResult,
    LeaveBalanceResult,
    LeaveDraft,
    PayrollSummary,
    ToolError,
    ToolResult,
)

# --------------------------------------------------------------------------- errors (T019)


@pytest.mark.parametrize(
    ("cls", "category"),
    [
        (errors.ConfigurationError, "configuration"),
        (errors.DatabaseError, "database"),
        (errors.RetrievalError, "retrieval"),
        (errors.ModelServiceError, "model_service"),
        (errors.NotFound, "not_found"),
        (errors.InvalidToken, "invalid_token"),
    ],
)
def test_error_categories(cls, category):
    err = cls()
    assert isinstance(err, errors.HCMError)
    assert err.category == category


def test_access_denied_carries_capability():
    err = errors.AccessDenied("payroll")
    assert err.capability == "payroll" and err.category == "access_denied"


def test_validation_error_carries_field_and_message():
    err = errors.ValidationError("end_date", "must be on or after start_date")
    assert (err.field, err.message, err.category) == (
        "end_date", "must be on or after start_date", "invalid_input")
    assert "end_date" in str(err)


def test_account_locked_carries_until():
    from datetime import UTC, datetime

    until = datetime(2026, 10, 25, 10, tzinfo=UTC)
    err = errors.AccountLocked(until)
    assert err.until == until and err.category == "account_locked"


def test_configuration_error_lists_variables():
    err = errors.ConfigurationError("bad config", variables=["API_JWT_SECRET"])
    assert err.variables == ["API_JWT_SECRET"]


# --------------------------------------------------------------------------- domain (T022)


def test_enum_values_match_data_model():
    assert {r.value for r in Role} == {"employee", "manager", "hr_admin", "admin"}
    assert {t.value for t in LeaveType} == {"annual", "sick", "casual", "unpaid", "other"}
    assert {s.value for s in LeaveStatus} == {"pending", "approved", "rejected", "cancelled"}
    assert {s.value for s in AttendanceStatus} == {"present", "remote", "absent", "leave"}
    assert {c.value for c in Channel} == {"chat", "api"}
    assert {a.value for a in AuditAction} == {
        "login_success", "login_failed", "account_locked", "logout", "session_expired",
        "access_denied", "leave_submitted", "password_changed", "user_created", "user_updated",
        "user_deactivated", "user_activated", "user_deleted", "admin_created",
    }


def test_authenticated_user_is_frozen():
    user = AuthenticatedUser(
        user_id="U0001", username="employee", email="employee@demo.hcm", role="employee",
        employee_id="E1001", display_name="Demo Employee", department="Engineering",
    )
    assert user.role is Role.EMPLOYEE
    with pytest.raises(pydantic.ValidationError):
        user.role = Role.HR_ADMIN  # type: ignore[misc]


def test_scope():
    assert Scope(kind="all", employee_ids=None).includes("anyone")
    team = Scope(kind="team", employee_ids=frozenset({"M1002", "E1001"}))
    assert team.includes("E1001") and not team.includes("E9999")
    with pytest.raises(pydantic.ValidationError):
        Scope(kind="self", employee_ids=None)  # only "all" may be unrestricted
    with pytest.raises(pydantic.ValidationError):
        Scope(kind="all", employee_ids=frozenset({"E1001"}))


def test_date_range():
    r = DateRange(start=date(2026, 10, 1), end=date(2026, 10, 25), label="this_month")
    assert r.days == 25
    with pytest.raises(pydantic.ValidationError):
        DateRange(start=date(2026, 10, 2), end=date(2026, 10, 1), label="x")


# --------------------------------------------------------------------------- results (T023)


def test_tool_result_success_and_failure_envelopes():
    ok = ToolResult[HeadcountResult].success(
        HeadcountResult(scope="all", total_active=3, by_department={"Eng": 3},
                        as_of=date(2026, 10, 25)),
        source="hr-db:employees", scope="all", is_demo=True,
    )
    body = json.loads(ok.model_dump_json())
    assert body["ok"] is True and body["error"] is None
    assert body["data"]["total_active"] == 3
    assert body["source"] == "hr-db:employees" and body["is_demo"] is True

    denied = ToolResult[HeadcountResult].failure("access_denied", "Not permitted for your role.")
    body = json.loads(denied.model_dump_json())
    assert body["ok"] is False and body["data"] is None
    assert body["error"] == {"code": "access_denied", "message": "Not permitted for your role."}


def test_tool_error_codes_are_closed():
    with pytest.raises(pydantic.ValidationError):
        ToolError(code="boom", message="x")


def test_ok_flag_consistent_with_payload():
    with pytest.raises(pydantic.ValidationError):
        ToolResult[HeadcountResult](ok=True, data=None, error=ToolError(code="no_data", message="x"))
    with pytest.raises(pydantic.ValidationError):
        ToolResult[HeadcountResult](ok=False, data=None, error=None)


def test_decimal_serializes_as_two_dp_string():
    balance = LeaveBalanceResult(
        employee_id="E1001", year=2026, as_of=date(2026, 10, 25),
        balances=[BalanceEntry(leave_type="annual", entitled=Decimal("20"), used=Decimal("3.5"),
                               pending=Decimal("2"), remaining=Decimal("14.5"))],
    )
    entry = json.loads(balance.model_dump_json())["balances"][0]
    assert entry == {"leave_type": "annual", "entitled": "20.00", "used": "3.50",
                     "pending": "2.00", "remaining": "14.50"}

    payroll = PayrollSummary(period="2026-09", currency="USD", gross_total=Decimal("1234.5"),
                             net_total=Decimal("1000.005"), headcount_paid=4, by_department=[])
    body = json.loads(payroll.model_dump_json())
    assert body["gross_total"] == "1234.50"
    assert body["net_total"] == "1000.01"  # ROUND_HALF_UP


def test_leave_draft_defaults():
    draft = LeaveDraft(draft_id="0b6c8a2e-7d0f-4a59-9a0e-5d1f0f3c2a11")
    assert draft.status is DraftStatus.INCOMPLETE
    assert draft.missing_fields == [] and draft.validation_errors == [] and draft.warnings == []
    assert draft.submitted_reference is None and draft.balance_remaining is None
    draft = draft.model_copy(update={"balance_remaining": Decimal("4")})
    assert json.loads(draft.model_dump_json())["balance_remaining"] == "4.00"


def test_citation_label():
    c = Citation(n=1, document_id="leave-policy", title="Leave Policy", section="Annual leave",
                 page=None, source_path="policies/leave.md")
    assert c.label == "[1] Leave Policy — Annual leave"


def test_user_record_repr_hides_password_hash():
    from datetime import datetime

    from hcm_lite.models.domain import UserRecord
    rec = UserRecord(id="u1", username="alice", email="alice@demo.hcm",
                     password_hash="pbkdf2_sha256$1$SECRETSALT$X",
                     role="employee", employee_id="E1", created_at=datetime(2026, 1, 1))
    assert "SECRETSALT" not in repr(rec) and "SECRETSALT" not in str(rec)


def test_payroll_period_year_range():
    import pydantic

    from hcm_lite.models.domain import PayrollTotalRecord
    base = dict(department="IT", headcount_paid=1, gross_total=1, net_total=1, currency="USD")
    assert PayrollTotalRecord(period="2026-10", **base).period == "2026-10"
    for bad in ("1899-01", "2100-01", "２０２６-10"):
        with pytest.raises(pydantic.ValidationError):
            PayrollTotalRecord(period=bad, **base)
