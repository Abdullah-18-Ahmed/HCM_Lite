"""Metrics service (contracts/services.md MetricsService, FR-011/FR-025–027).

Every public method authorizes and scopes via :class:`~hcm_lite.services.authz.Authz` before
any repository call (research D-06); a denial raises ``AccessDenied`` (audited by authz).
Figures come from SQL ``COUNT``/``SUM``/``GROUP BY`` aggregations where the repositories
provide them; repository-filtered rows are used only for derived values the schema does not
store (lateness, per-department attendance rollups) and to propagate ``is_demo``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from hcm_lite.db.repositories import (
    AttendanceRepo,
    EmployeeRepo,
    HolidayRepo,
    LeaveRepo,
    PayrollRepo,
)
from hcm_lite.errors import ValidationError
from hcm_lite.models.domain import (
    AttendanceRecord,
    AttendanceStatus,
    AuthenticatedUser,
    DateRange,
    EmployeeRecord,
    LeaveStatus,
)
from hcm_lite.models.requests import EmployeeSearchFilters, PeriodArgs
from hcm_lite.models.results import (
    AttendanceSummary,
    DepartmentAttendance,
    EmployeeSearchResult,
    EmployeeSummary,
    HeadcountResult,
    LateComersResult,
    LateEntry,
    LeaveSummary,
    PayrollDepartment,
    PayrollSummary,
    PendingLeave,
    PeriodRange,
    ProfileResult,
    ToolResult,
)
from hcm_lite.services.authz import Authz, Capability
from hcm_lite.services.periods import resolve_period, working_days

__all__ = ["MetricsService"]

_ALL_LEAVE_STATUSES = tuple(s.value for s in LeaveStatus)
_MAX_LATE_ENTRIES = 50


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _attendance_rate(present: int, remote: int, records: int, on_leave: int) -> float:
    """Attended days over scheduled days (records minus approved-leave days), 1 dp."""
    scheduled = records - on_leave
    if scheduled <= 0:
        return 0.0
    return round((present + remote) / scheduled * 100, 1)


def _is_late(row: AttendanceRecord, grace: int) -> bool:
    """data-model.md: late = present/remote and check_in > scheduled_start + grace."""
    return (row.status in (AttendanceStatus.PRESENT, AttendanceStatus.REMOTE)
            and row.check_in is not None
            and _minutes(row.check_in) > _minutes(row.scheduled_start) + grace)


def _employee_index(employees: list[EmployeeRecord]) -> dict[str, EmployeeRecord]:
    return {e.id: e for e in employees}


class MetricsService:
    def __init__(self, session_factory: Any, authz: Authz, *,
                 late_grace_minutes: int = 0, today: date | None = None) -> None:
        self._sf = session_factory
        self._authz = authz
        self._grace = late_grace_minutes
        self._today_default = today

    def _today(self, today: date | None) -> date:
        return today or self._today_default or date.today()

    def _range(self, range_args: PeriodArgs | None, today: date, *,
               default: str, full_month: bool = False) -> DateRange:
        period = None if range_args is None else range_args.period
        start = None if range_args is None else range_args.start_date
        end = None if range_args is None else range_args.end_date
        resolved = resolve_period(period, today=today, start_date=start, end_date=end,
                                  default=default)
        if full_month and resolved.label == "this_month":
            # Exception (contracts/agent-tools.md): leave summaries use the full month so
            # already-booked future leave in the month is counted. Keep the keyword label.
            full = resolve_period(f"{today.year:04d}-{today.month:02d}", today=today)
            resolved = DateRange(start=full.start, end=full.end, label=resolved.label)
        return resolved

    # ------------------------------------------------------------------ self

    async def my_profile(self, user: AuthenticatedUser) -> ToolResult[ProfileResult]:
        await self._authz.require(user, Capability.OWN_DATA)
        async with self._sf() as session:
            employees = EmployeeRepo(session)
            employee = await employees.get(user.employee_id)
            manager = (await employees.get(employee.manager_id)
                       if employee is not None and employee.manager_id else None)
        if employee is None:
            return ToolResult.failure("not_found", "Employee record not found",
                                      source="hr-db:employees", scope="self")
        return ToolResult.success(
            ProfileResult(employee_id=employee.id, full_name=employee.full_name,
                          department=employee.department, job_title=employee.job_title,
                          manager_name=manager.full_name if manager else None,
                          hire_date=employee.hire_date),
            source="hr-db:employees", scope="self", is_demo=employee.is_demo)

    # ------------------------------------------------------------------ team / all

    async def headcount(self, user: AuthenticatedUser, department: str | None = None, *,
                        today: date | None = None) -> ToolResult[HeadcountResult]:
        await self._authz.require(user, Capability.METRICS)
        scope = await self._authz.resolve_scope(user)
        as_of = self._today(today)
        async with self._sf() as session:
            employees = EmployeeRepo(session)
            by_department = await employees.headcount_by_department(
                employee_ids=scope.employee_ids, department=department)
            rows = await employees.list(employee_ids=scope.employee_ids,
                                        department=department) if by_department else []
        return ToolResult.success(
            HeadcountResult(scope=scope.kind, total_active=sum(by_department.values()),
                            by_department=dict(sorted(by_department.items())), as_of=as_of),
            source="hr-db:employees", scope=scope.kind,
            is_demo=any(r.is_demo for r in rows))

    async def attendance_summary(self, user: AuthenticatedUser,
                                 range_args: PeriodArgs | None = None,
                                 department: str | None = None, *,
                                 today: date | None = None) -> ToolResult[AttendanceSummary]:
        await self._authz.require(user, Capability.OWN_DATA)
        scope = await self._authz.resolve_scope(user)
        as_of = self._today(today)
        period = self._range(range_args, as_of, default="this_month")
        async with self._sf() as session:
            counts = await AttendanceRepo(session).count_by_status(
                employee_ids=scope.employee_ids, start=period.start, end=period.end,
                department=department)
            rows = await AttendanceRepo(session).list(
                employee_ids=scope.employee_ids, start=period.start, end=period.end,
                department=department)
            employees = _employee_index(await EmployeeRepo(session).list(
                employee_ids=scope.employee_ids))
            holidays = await HolidayRepo(session).between(period.start, period.end)
        present = counts.get(AttendanceStatus.PRESENT.value, 0)
        remote = counts.get(AttendanceStatus.REMOTE.value, 0)
        absent = counts.get(AttendanceStatus.ABSENT.value, 0)
        on_leave = counts.get(AttendanceStatus.LEAVE.value, 0)
        records = present + remote + absent + on_leave
        if records == 0:
            return ToolResult.failure(
                "no_data", "No attendance records in this period",
                source="hr-db:attendance", period=period.label, scope=scope.kind)
        late = sum(1 for r in rows if _is_late(r, self._grace))
        per_department: dict[str, dict[str, int]] = {}
        for row in rows:
            dept = employees[row.employee_id].department
            bucket = per_department.setdefault(
                dept, {"present": 0, "remote": 0, "absent": 0, "leave": 0, "late": 0})
            bucket[row.status.value] += 1
            if _is_late(row, self._grace):
                bucket["late"] += 1
        by_department = [
            DepartmentAttendance(
                department=dept, records=sum(bucket[s] for s in counts), present=bucket["present"],
                remote=bucket["remote"], absent=bucket["absent"], on_leave=bucket["leave"],
                late=bucket["late"],
                attendance_rate=_attendance_rate(bucket["present"], bucket["remote"],
                                                 sum(bucket[s] for s in counts),
                                                 bucket["leave"]))
            for dept, bucket in sorted(per_department.items())
        ]
        return ToolResult.success(
            AttendanceSummary(
                period=PeriodRange(start_date=period.start, end_date=period.end,
                                   label=period.label),
                working_days=working_days(period.start, period.end, {h.date for h in holidays}),
                records=records, present=present, remote=remote, absent=absent,
                on_leave=on_leave, late=late,
                attendance_rate=_attendance_rate(present, remote, records, on_leave),
                by_department=by_department),
            source="hr-db:attendance", period=period.label, scope=scope.kind,
            is_demo=any(r.is_demo for r in rows))

    async def late_comers(self, user: AuthenticatedUser, range_args: PeriodArgs | None = None,
                          department: str | None = None, *,
                          today: date | None = None) -> ToolResult[LateComersResult]:
        await self._authz.require(user, Capability.METRICS)
        scope = await self._authz.resolve_scope(user)
        as_of = self._today(today)
        period = self._range(range_args, as_of, default="today")
        async with self._sf() as session:
            rows = await AttendanceRepo(session).list(
                employee_ids=scope.employee_ids, start=period.start, end=period.end,
                department=department)
            late_ids = {r.employee_id for r in rows if _is_late(r, self._grace)}
            employees = _employee_index(await EmployeeRepo(session).list(
                employee_ids=late_ids)) if late_ids else {}
        late_rows = sorted((r for r in rows if _is_late(r, self._grace)),
                           key=lambda r: (r.date, r.employee_id))
        if not late_rows:
            return ToolResult.failure(
                "no_data", "No late arrivals in this period",
                source="hr-db:attendance", period=period.label, scope=scope.kind)
        entries = [
            LateEntry(employee_id=r.employee_id, full_name=employees[r.employee_id].full_name,
                      department=employees[r.employee_id].department, date=r.date,
                      check_in=r.check_in or "",
                      minutes_late=_minutes(r.check_in) - _minutes(r.scheduled_start))
            for r in late_rows[:_MAX_LATE_ENTRIES]
        ]
        return ToolResult.success(
            LateComersResult(
                period=PeriodRange(start_date=period.start, end_date=period.end,
                                   label=period.label),
                count=len(late_rows), entries=entries, truncated=len(late_rows) > len(entries)),
            source="hr-db:attendance", period=period.label, scope=scope.kind,
            is_demo=any(r.is_demo for r in rows))

    async def leave_summary(self, user: AuthenticatedUser, range_args: PeriodArgs | None = None,
                            status: str | LeaveStatus | None = None,
                            department: str | None = None, *,
                            today: date | None = None) -> ToolResult[LeaveSummary]:
        await self._authz.require(user, Capability.OWN_DATA)
        scope = await self._authz.resolve_scope(user)
        as_of = self._today(today)
        period = self._range(range_args, as_of, default="this_month", full_month=True)
        if status is not None and str(status) not in _ALL_LEAVE_STATUSES:
            raise ValidationError("status", "unknown leave status")
        status_filter = LeaveStatus(status) if status is not None else None
        # The department filter intersects with the scope: only employees that are BOTH in
        # scope and in the department contribute (a manager can never widen to the org).
        async with self._sf() as session:
            employees_repo = EmployeeRepo(session)
            scoped = await employees_repo.list(employee_ids=scope.employee_ids,
                                               department=department)
            ids = {e.id for e in scoped}
            leave = LeaveRepo(session)
            ids_param = ids if scope.kind != "all" or department is not None else None
            by_status_all = await leave.count_by_status(
                employee_ids=ids_param, start=period.start, end=period.end)
            by_type = await leave.sum_days_by_type(
                employee_ids=ids_param, start=period.start, end=period.end,
                statuses=({status_filter} if status_filter is not None
                          else _ALL_LEAVE_STATUSES))
            approved_days = await leave.sum_days_by_type(
                employee_ids=ids_param, start=period.start, end=period.end,
                statuses=(LeaveStatus.APPROVED,))
            demo_rows = await leave.list_for_employees(
                employee_ids=ids_param, start=period.start, end=period.end, limit=1)
            pending_rows: list = []
            if scope.kind != "self":
                pending_rows = await leave.list_for_employees(
                    employee_ids=ids_param, start=period.start, end=period.end,
                    statuses=(LeaveStatus.PENDING,), limit=25)
            pending_people = _employee_index(await employees_repo.list(
                employee_ids={r.employee_id for r in pending_rows})) if pending_rows else {}
        by_status = {s: n for s, n in by_status_all.items()
                     if status_filter is None or s == status_filter.value}
        if not by_status:
            return ToolResult.failure(
                "no_data", "No leave requests in this period",
                source="hr-db:leave_requests", period=period.label, scope=scope.kind)
        return ToolResult.success(
            LeaveSummary(
                period=PeriodRange(start_date=period.start, end_date=period.end,
                                   label=period.label),
                by_status=by_status, by_type=dict(sorted(by_type.items())),
                total_days_approved=sum(approved_days.values()),
                pending=[
                    PendingLeave(reference=r.id, employee=pending_people[r.employee_id].full_name,
                                 start_date=r.start_date, end_date=r.end_date, days=r.working_days)
                    for r in pending_rows]),
            source="hr-db:leave_requests", period=period.label, scope=scope.kind,
            is_demo=any(r.is_demo for r in demo_rows))

    async def payroll_summary(self, user: AuthenticatedUser, period: str | None = None,
                              department: str | None = None, *,
                              today: date | None = None) -> ToolResult[PayrollSummary]:
        await self._authz.require(user, Capability.PAYROLL)
        resolved = resolve_period(period, today=self._today(today), default="last_month")
        period_label = f"{resolved.start:%Y-%m}"
        async with self._sf() as session:
            payroll = PayrollRepo(session)
            rows = await payroll.by_period(period_label, department=department)
            headcount, gross, net = await payroll.totals_for_period(
                period_label, department=department)
        if not rows:
            return ToolResult.failure(
                "no_data", "No payroll totals for this period",
                source="hr-db:payroll_totals", period=period_label, scope="all")
        return ToolResult.success(
            PayrollSummary(
                period=period_label, currency=rows[0].currency, gross_total=gross, net_total=net,
                headcount_paid=headcount,
                by_department=[
                    PayrollDepartment(department=r.department, headcount_paid=r.headcount_paid,
                                      gross_total=r.gross_total, net_total=r.net_total)
                    for r in rows]),
            source="hr-db:payroll_totals", period=period_label, scope="all",
            is_demo=any(r.is_demo for r in rows))

    async def search_employees(self, user: AuthenticatedUser,
                               filters: EmployeeSearchFilters, *,
                               today: date | None = None) -> ToolResult[EmployeeSearchResult]:
        await self._authz.require(user, Capability.EMPLOYEE_SEARCH)
        scope = await self._authz.resolve_scope(user)
        async with self._sf() as session:
            rows = await EmployeeRepo(session).search(
                employee_ids=scope.employee_ids, name=filters.name,
                department=filters.department, job_title=filters.job_title,
                status=filters.status)
        return ToolResult.success(
            EmployeeSearchResult(
                count=len(rows),
                employees=[
                    EmployeeSummary(employee_id=r.id, full_name=r.full_name,
                                    department=r.department, job_title=r.job_title,
                                    employment_status=r.employment_status)
                    for r in rows]),
            source="hr-db:employees", scope=scope.kind,
            is_demo=any(r.is_demo for r in rows))
