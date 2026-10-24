"""T023: request models (`hcm_lite/models/requests.py`); all extra="forbid"."""

from __future__ import annotations

from datetime import date

import pydantic
import pytest

from hcm_lite.models.domain import LeaveType
from hcm_lite.models.requests import (
    ChatMessage,
    DepartmentFilter,
    EmployeeSearchFilters,
    LeaveDraftRequest,
    PeriodArgs,
    PolicyQuery,
)

ALL = [ChatMessage, DepartmentFilter, EmployeeSearchFilters, LeaveDraftRequest, PeriodArgs,
       PolicyQuery]


@pytest.mark.parametrize("model", ALL)
def test_extra_fields_forbidden(model):
    assert model.model_config.get("extra") == "forbid"
    with pytest.raises(pydantic.ValidationError):
        model.model_validate({"role": "hr_admin", "user_id": "U0003"})


@pytest.mark.parametrize("model", ALL)
def test_no_identity_fields(model):
    assert not {"role", "user_id", "employee_id"} & set(model.model_fields)


# --------------------------------------------------------------------------- PeriodArgs


@pytest.mark.parametrize(
    "period",
    ["today", "yesterday", "this_week", "last_week", "this_month", "last_month",
     "this_quarter", "2026-09", None],
)
def test_period_args_accepts_contract_values(period):
    assert PeriodArgs(period=period).period == period


@pytest.mark.parametrize("period", ["next_year", "2026-13", "September", "2026-9"])
def test_period_args_rejects_unknown(period):
    with pytest.raises(pydantic.ValidationError):
        PeriodArgs(period=period)


def test_period_args_iso_range():
    p = PeriodArgs(start_date="2026-10-01", end_date="2026-10-09")
    assert (p.start_date, p.end_date) == (date(2026, 10, 1), date(2026, 10, 9))


def test_period_args_requires_both_bounds():
    with pytest.raises(pydantic.ValidationError):
        PeriodArgs(start_date="2026-10-01")
    with pytest.raises(pydantic.ValidationError):
        PeriodArgs(end_date="2026-10-01")


def test_period_args_bad_date():
    with pytest.raises(pydantic.ValidationError):
        PeriodArgs(start_date="01/10/2026", end_date="2026-10-09")


# --------------------------------------------------------------------------- filters


def test_department_filter():
    assert DepartmentFilter().department is None
    assert DepartmentFilter(department=" Engineering ").department == "Engineering"
    with pytest.raises(pydantic.ValidationError):
        DepartmentFilter(department="x" * 61)


def test_employee_search_requires_at_least_one_field():
    with pytest.raises(pydantic.ValidationError):
        EmployeeSearchFilters()
    with pytest.raises(pydantic.ValidationError):
        EmployeeSearchFilters(name="  ")
    assert EmployeeSearchFilters(name="Ali").name == "Ali"
    assert EmployeeSearchFilters(status="inactive").status == "inactive"
    with pytest.raises(pydantic.ValidationError):
        EmployeeSearchFilters(status="fired")


def test_policy_query_length():
    with pytest.raises(pydantic.ValidationError):
        PolicyQuery(query="ab")
    with pytest.raises(pydantic.ValidationError):
        PolicyQuery(query="x" * 501)
    assert PolicyQuery(query="abc").query == "abc"
    assert PolicyQuery(query="x" * 500, doc_type="policy").doc_type == "policy"


# --------------------------------------------------------------------------- leave draft


def test_leave_draft_request_all_optional():
    r = LeaveDraftRequest()
    assert r.leave_type is None and r.start_date is None and r.draft_id is None


def test_leave_draft_request_fields():
    r = LeaveDraftRequest(
        leave_type="annual", start_date="2026-11-02", end_date="2026-11-03", reason="Family",
        draft_id="0b6c8a2e-7d0f-4a59-9a0e-5d1f0f3c2a11",
    )
    assert r.leave_type is LeaveType.ANNUAL
    assert r.start_date == date(2026, 11, 2)
    with pytest.raises(pydantic.ValidationError):
        LeaveDraftRequest(leave_type="vacation")
    with pytest.raises(pydantic.ValidationError):
        LeaveDraftRequest(reason="x" * 501)
    with pytest.raises(pydantic.ValidationError):
        LeaveDraftRequest(draft_id="not-a-uuid")


# --------------------------------------------------------------------------- chat


def test_chat_message_limit():
    assert ChatMessage(message="x" * 4000).message == "x" * 4000
    with pytest.raises(pydantic.ValidationError):
        ChatMessage(message="x" * 4001)
    with pytest.raises(pydantic.ValidationError):
        ChatMessage(message="   ")
