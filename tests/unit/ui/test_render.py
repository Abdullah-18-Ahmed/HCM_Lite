"""T049: dashboard markdown rendering (hcm_lite/ui/render.py).

Markdown tables carry period labels and the "Demo data" label; an employee render never
contains another employee's name (US1 scenario 4) — except the employee's own manager name,
which is part of their own profile (ProfileResult.manager_name).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from hcm_lite.models.domain import Role
from hcm_lite.services.dashboard_service import DashboardService
from hcm_lite.services.leave_service import LeaveService
from hcm_lite.services.metrics_service import MetricsService
from hcm_lite.ui.render import render_dashboard, render_error
from tests.conftest import TODAY


def _names(tmp_path) -> dict[str, str]:
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db:
        return dict(db.execute("SELECT id, full_name FROM employees").fetchall())


@pytest.fixture
def dashboard(sf, authz, auditor):
    return DashboardService(
        MetricsService(sf, authz, late_grace_minutes=0, today=TODAY),
        LeaveService(sf, authz, auditor, today=TODAY),
    )


async def test_employee_render_is_markdown_with_periods_and_demo_label(dashboard, make_user):
    text = render_dashboard(await dashboard.for_user(make_user(Role.EMPLOYEE), TODAY))
    assert "Demo data" in text
    assert "|" in text and "---" in text  # markdown tables
    # Attendance is this month to date (2026-10-25).
    assert "**Period:** this_month (2026-10-01 to 2026-10-25)" in text
    # The balances table states its as-of date.
    assert "**As of:** 2026-10-25" in text
    assert "| Type | Entitled | Used | Pending | Remaining |" in text
    assert "| Reference | Type | Start | End | Days | Status |" in text
    assert "Payroll" not in text  # no payroll section for an employee


async def test_manager_and_hr_renders(dashboard, make_user):
    manager = render_dashboard(await dashboard.for_user(make_user(Role.MANAGER), TODAY))
    assert "Demo data" in manager
    assert "| Department | Active |" in manager  # team headcount table
    # The pending-leave section resolves this_month to the full calendar month.
    assert "**Period:** this_month (2026-10-01 to 2026-10-31)" in manager
    assert "No records" in manager  # "late today" on a Sunday is no_data, shown honestly

    hr = render_dashboard(await dashboard.for_user(make_user(Role.HR_ADMIN), TODAY))
    assert "| Department | Headcount paid | Gross | Net |" in hr
    assert "**Period:** 2026-09" in hr  # payroll last month


async def test_employee_render_has_no_other_employees_name(dashboard, make_user, tmp_path):
    text = render_dashboard(await dashboard.for_user(make_user(Role.EMPLOYEE), TODAY))
    names = _names(tmp_path)
    own = names["E1001"]
    manager_name = names["M1002"]  # shown as the employee's own manager (own profile)
    assert own in text
    for employee_id, name in names.items():
        if name in (own, manager_name):
            continue
        assert name not in text, f"leaked {employee_id}"


def test_render_error_shows_the_safe_message_only():
    message = "The HR database is temporarily unavailable."
    text = render_error(message)
    assert message in text
    assert "Traceback" not in text and "password" not in text.lower()
