"""Dashboard service (contracts/services.md DashboardService, constitution Art. X).

One read-only dashboard per role, composed only of the shared Metrics/Leave services so the
dashboard, the agent tools and the API always show the same figures (FR-012). Each section is
fetched independently: a denial puts the section name in ``withheld``, any other failure in
``unavailable``; neither breaks the remaining sections.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from hcm_lite.errors import AccessDenied
from hcm_lite.models.domain import AuthenticatedUser, Role
from hcm_lite.models.requests import PeriodArgs
from hcm_lite.models.results import DashboardData, ToolResult

__all__ = ["DashboardService"]

_THIS_MONTH = PeriodArgs(period="this_month")
_TODAY = PeriodArgs(period="today")


class DashboardService:
    def __init__(self, metrics: Any, leave: Any) -> None:
        self._metrics = metrics
        self._leave = leave

    async def for_user(self, user: AuthenticatedUser, today: date) -> DashboardData:
        sections: dict[str, ToolResult[Any]] = {}
        withheld: list[str] = []
        unavailable: list[str] = []

        async def add(name: str, call: Any) -> None:
            try:
                sections[name] = await call
            except AccessDenied:  # an HCMError subclass; checked first
                withheld.append(name)
            except Exception:  # any other failure never breaks the remaining sections
                unavailable.append(name)

        if user.role == Role.EMPLOYEE:
            await add("profile", self._metrics.my_profile(user))
            await add("my_attendance",
                      self._metrics.attendance_summary(user, _THIS_MONTH, today=today))
            await add("my_balances", self._leave.my_balance(user, today=today))
            await add("my_leave_requests", self._leave.my_requests(user, limit=10))
        elif user.role == Role.MANAGER:
            await add("team_headcount", self._metrics.headcount(user, today=today))
            await add("team_attendance",
                      self._metrics.attendance_summary(user, _THIS_MONTH, today=today))
            await add("team_late_today",
                      self._metrics.late_comers(user, _TODAY, today=today))
            await add("team_pending_leave",
                      self._metrics.leave_summary(user, _THIS_MONTH, today=today))
            await add("my_balances", self._leave.my_balance(user, today=today))
        else:  # hr_admin
            await add("headcount", self._metrics.headcount(user, today=today))
            await add("org_attendance",
                      self._metrics.attendance_summary(user, _THIS_MONTH, today=today))
            await add("leave_summary",
                      self._metrics.leave_summary(user, _THIS_MONTH, today=today))
            await add("payroll_last_month",
                      self._metrics.payroll_summary(user, period="last_month", today=today))
        return DashboardData(role=user.role, sections=sections, withheld=withheld,
                             unavailable=unavailable)
