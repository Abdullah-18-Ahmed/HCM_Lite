"""T048: DashboardService.for_user per role (contracts/services.md DashboardService).

Sections come only from the shared Metrics/Leave services; every dashboard figure equals the
direct service call (FR-012), a failure puts the section in ``unavailable`` and a denial in
``withheld``.
"""

from __future__ import annotations

from hcm_lite.errors import AccessDenied, DatabaseError
from hcm_lite.models.requests import PeriodArgs
from hcm_lite.models.results import DashboardData
from hcm_lite.services.dashboard_service import DashboardService
from tests.conftest import TODAY
from tests.unit.services.conftest import sql_one, team_ids

EMPLOYEE_SECTIONS = {"profile", "my_attendance", "my_balances", "my_leave_requests"}
MANAGER_SECTIONS = {"team_headcount", "team_attendance", "team_late_today",
                    "team_pending_leave", "my_balances"}
HR_SECTIONS = {"headcount", "org_attendance", "leave_summary", "payroll_last_month"}


async def test_employee_sections_and_parity(dashboard, metrics, leave, make_user):
    user = make_user("employee")
    data = await dashboard.for_user(user, TODAY)
    assert isinstance(data, DashboardData) and data.role == "employee"
    assert set(data.sections) == EMPLOYEE_SECTIONS
    assert data.withheld == [] and data.unavailable == []
    this_month = PeriodArgs(period="this_month")
    assert data.sections["profile"].model_dump() == (await metrics.my_profile(user)).model_dump()
    assert data.sections["my_attendance"].model_dump() == (
        await metrics.attendance_summary(user, this_month, today=TODAY)).model_dump()
    assert data.sections["my_balances"].model_dump() == (
        await leave.my_balance(user, today=TODAY)).model_dump()
    assert data.sections["my_leave_requests"].model_dump() == (
        await leave.my_requests(user, limit=10)).model_dump()


async def test_manager_sections_and_parity(dashboard, metrics, leave, make_user, tmp_path):
    user = make_user("manager")
    data = await dashboard.for_user(user, TODAY)
    assert data.role == "manager" and set(data.sections) == MANAGER_SECTIONS
    assert data.withheld == [] and data.unavailable == []
    this_month = PeriodArgs(period="this_month")
    assert data.sections["team_headcount"].model_dump() == (
        await metrics.headcount(user, today=TODAY)).model_dump()
    assert data.sections["team_attendance"].model_dump() == (
        await metrics.attendance_summary(user, this_month, today=TODAY)).model_dump()
    # 2026-10-25 is a Sunday, so "today" has no attendance rows: no_data, not a failure.
    assert data.sections["team_late_today"].error.code == "no_data"
    assert data.sections["team_pending_leave"].model_dump() == (
        await metrics.leave_summary(user, this_month, today=TODAY)).model_dump()
    assert data.sections["my_balances"].model_dump() == (
        await leave.my_balance(user, today=TODAY)).model_dump()
    # Team figures cover only direct reports plus the manager (US1 scenario 5).
    ids = team_ids(tmp_path)
    marks = ",".join("?" for _ in ids)
    assert data.sections["team_headcount"].data.total_active == sql_one(
        tmp_path, f"SELECT COUNT(*) FROM employees WHERE employment_status='active'"
                  f" AND id IN ({marks})", tuple(sorted(ids)))


async def test_hr_sections_and_parity(dashboard, metrics, make_user):
    user = make_user("hr_admin")
    data = await dashboard.for_user(user, TODAY)
    assert data.role == "hr_admin" and set(data.sections) == HR_SECTIONS
    assert data.withheld == [] and data.unavailable == []
    this_month = PeriodArgs(period="this_month")
    assert data.sections["headcount"].model_dump() == (
        await metrics.headcount(user, today=TODAY)).model_dump()
    assert data.sections["org_attendance"].model_dump() == (
        await metrics.attendance_summary(user, this_month, today=TODAY)).model_dump()
    assert data.sections["leave_summary"].model_dump() == (
        await metrics.leave_summary(user, this_month, today=TODAY)).model_dump()
    assert data.sections["payroll_last_month"].model_dump() == (
        await metrics.payroll_summary(user, period="last_month", today=TODAY)).model_dump()


async def test_a_failure_marks_the_section_unavailable(metrics, leave, make_user):
    async def boom(user, range_args, department=None, *, today=None):
        raise DatabaseError("The HR database is unavailable")

    original = metrics.attendance_summary
    metrics.attendance_summary = boom
    section_of = {"employee": "my_attendance", "manager": "team_attendance",
                  "hr_admin": "org_attendance"}
    try:
        dashboard = DashboardService(metrics, leave)
        for role, section in section_of.items():
            data = await dashboard.for_user(make_user(role), TODAY)
            assert data.unavailable == [section]
            assert section not in data.sections and data.withheld == []
    finally:
        metrics.attendance_summary = original


async def test_a_denial_marks_the_section_withheld(metrics, leave, make_user):
    async def denied(user, period=None, department=None, *, today=None):
        raise AccessDenied("payroll")

    original = metrics.payroll_summary
    metrics.payroll_summary = denied
    try:
        dashboard = DashboardService(metrics, leave)
        data = await dashboard.for_user(make_user("hr_admin"), TODAY)
        assert data.withheld == ["payroll_last_month"]
        assert "payroll_last_month" not in data.sections
        assert data.unavailable == []
    finally:
        metrics.payroll_summary = original


async def test_sections_are_fetched_independently(dashboard, make_user):
    """One failing section never removes the others."""
    data = await dashboard.for_user(make_user("hr_admin"), TODAY)
    assert len(data.sections) == 4  # all sections present on the seeded DB
    assert all(r.ok for r in data.sections.values())
