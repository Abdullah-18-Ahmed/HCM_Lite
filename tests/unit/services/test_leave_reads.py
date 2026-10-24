"""T047: LeaveService.my_balance / my_requests (self-only reads) on the seeded temp DB.

Expectations are derived from direct SQL on the same database; remaining is
entitled − used − pending, with pending days summed from the caller's own pending requests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from hcm_lite.db.repositories import EmployeeRepo, LeaveRepo, UserRepo
from hcm_lite.models.domain import (
    EmployeeRecord,
    EmploymentStatus,
    LeaveRequestRecord,
    LeaveSource,
    LeaveStatus,
    LeaveType,
    Role,
    UserRecord,
)
from tests.conftest import TODAY
from tests.unit.services.conftest import sql_all


def _expected_balances(tmp_path, employee_id: str, year: int = 2026) -> dict[str, dict]:
    rows = sql_all(
        tmp_path, "SELECT leave_type, entitled, used FROM leave_balances"
                  " WHERE employee_id = ? AND year = ?", (employee_id, year))
    pending = dict(sql_all(
        tmp_path, "SELECT leave_type, SUM(working_days) FROM leave_requests"
                  " WHERE employee_id = ? AND status = 'pending'"
                  " AND end_date >= ? AND start_date <= ? GROUP BY leave_type",
        (employee_id, f"{year}-01-01", f"{year}-12-31")))
    return {
        lt: {"entitled": Decimal(ent), "used": Decimal(used),
             "pending": Decimal(pending.get(lt, 0)),
             "remaining": Decimal(ent) - Decimal(used) - Decimal(pending.get(lt, 0))}
        for lt, ent, used in rows
    }


async def _add_requests(sf, records) -> None:
    async with sf() as session, session.begin():
        await LeaveRepo(session).insert_many(records)


# --------------------------------------------------------------------------- my_balance


async def test_my_balance_only_the_callers(leave, make_user, tmp_path):
    employee = await leave.my_balance(make_user(Role.EMPLOYEE))
    manager = await leave.my_balance(make_user(Role.MANAGER))
    assert employee.ok and employee.data.employee_id == "E1001"
    assert manager.ok and manager.data.employee_id == "M1002"
    assert employee.scope == "self" and employee.source == "hr-db:leave_balances"
    assert employee.data.year == 2026 and employee.data.as_of == TODAY
    assert employee.is_demo is True


async def test_my_balance_remaining_formula(leave, make_user, tmp_path):
    for role, eid in ((Role.EMPLOYEE, "E1001"), (Role.MANAGER, "M1002")):
        result = await leave.my_balance(make_user(role))
        expected = _expected_balances(tmp_path, eid)
        got = {b.leave_type: b for b in result.data.balances}
        assert set(got) == set(expected)
        for leave_type, exp in expected.items():
            entry = got[leave_type]
            assert (entry.entitled, entry.used, entry.pending) == (
                exp["entitled"], exp["used"], exp["pending"])
            assert entry.remaining == exp["remaining"]  # entitled − used − pending
    # The seed guarantees E1001 a pending annual request inside October.
    employee = await leave.my_balance(make_user(Role.EMPLOYEE))
    annual = next(b for b in employee.data.balances if b.leave_type == LeaveType.ANNUAL)
    assert annual.pending >= 1


async def test_my_balance_leave_type_filter(leave, make_user, tmp_path):
    result = await leave.my_balance(make_user(Role.EMPLOYEE), leave_type="annual")
    expected = _expected_balances(tmp_path, "E1001")
    assert result.ok and [b.leave_type for b in result.data.balances] == [LeaveType.ANNUAL]
    entry = result.data.balances[0]
    assert entry.remaining == expected["annual"]["remaining"]


async def test_my_balance_no_rows_no_data(leave, sf, make_user, tmp_path):
    # A brand-new non-demo employee with no balance rows for the year.
    async with sf() as session, session.begin():
        await EmployeeRepo(session).insert(EmployeeRecord(
            id="E9999", full_name="New Employee", department="Engineering",
            job_title="Software Engineer", employment_status=EmploymentStatus.ACTIVE,
            hire_date=date(2020, 1, 1), manager_id="M1002", is_demo=False))
        await UserRepo(session).insert(UserRecord(
            id="U0099", username="newemp", password_hash="pbkdf2_sha256$1$s$h",
            role=Role.EMPLOYEE, employee_id="E9999", is_demo=False,
            created_at=datetime(2026, 10, 25, tzinfo=UTC)))
    user = make_user(Role.EMPLOYEE, user_id="U0099", username="newemp", employee_id="E9999")
    result = await leave.my_balance(user)
    assert not result.ok and result.error.code == "no_data"
    assert result.source == "hr-db:leave_balances" and result.scope == "self"


# --------------------------------------------------------------------------- my_requests


async def test_my_requests_only_the_callers_newest_first(leave, make_user, tmp_path):
    result = await leave.my_requests(make_user(Role.EMPLOYEE))
    expected = [r[0] for r in sql_all(
        tmp_path, "SELECT id FROM leave_requests WHERE employee_id='E1001'"
                  " ORDER BY created_at DESC, id DESC")]
    assert result.ok and result.scope == "self" and result.source == "hr-db:leave_requests"
    assert result.data.count == len(result.data.requests) == len(expected)
    assert [r.reference for r in result.data.requests] == expected
    rows = dict(sql_all(
        tmp_path, "SELECT id, leave_type || '|' || status FROM leave_requests"
                  " WHERE employee_id='E1001'"))
    for item in result.data.requests:
        assert rows[item.reference] == f"{item.leave_type}|{item.status}"


async def test_my_requests_limit_is_at_most_ten(leave, sf, make_user, tmp_path):
    records = [
        LeaveRequestRecord(
            id=f"LR-20260101-{i:04d}", employee_id="E1001", leave_type=LeaveType.CASUAL,
            start_date=date(2026, 1, 5 + i % 20), end_date=date(2026, 1, 6 + i % 20),
            working_days=2, reason="unit test", status=LeaveStatus.PENDING,
            source=LeaveSource.SEED, idempotency_key=None, created_by="U0001",
            created_at=datetime(2026, 10, 26, i, 0, tzinfo=UTC), is_demo=False)
        for i in range(12)
    ]
    await _add_requests(sf, records)
    result = await leave.my_requests(make_user(Role.EMPLOYEE))
    expected = [r[0] for r in sql_all(
        tmp_path, "SELECT id FROM leave_requests WHERE employee_id='E1001'"
                  " ORDER BY created_at DESC, id DESC LIMIT 10")]
    assert result.data.count == 10
    assert [r.reference for r in result.data.requests] == expected
    assert expected[0].startswith("LR-20260101-")  # the newest inserted row leads


async def test_my_requests_none_no_data(leave, sf, make_user):
    async with sf() as session, session.begin():
        await EmployeeRepo(session).insert(EmployeeRecord(
            id="E9999", full_name="New Employee", department="Engineering",
            job_title="Software Engineer", employment_status=EmploymentStatus.ACTIVE,
            hire_date=date(2020, 1, 1), manager_id="M1002", is_demo=False))
    user = make_user(Role.EMPLOYEE, employee_id="E9999")
    result = await leave.my_requests(user)
    assert not result.ok and result.error.code == "no_data"
    assert result.source == "hr-db:leave_requests" and result.scope == "self"
