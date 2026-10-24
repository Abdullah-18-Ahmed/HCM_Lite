"""T046: MetricsService figures, scoping and denials on the seeded temp DB.

Every expected figure is derived with direct SQL on the same seeded database (SC-002, the
phase's independent test), never from the service's own output. Deterministic structure from
the seed (research D-13) supplies the guaranteed rows: M1002's team is Engineering-only,
E1001 has a pending October request, and 2026-10-25 is a Sunday (no attendance "today").
"""

from __future__ import annotations

from datetime import date

import pytest

from hcm_lite.db.repositories import AttendanceRepo
from hcm_lite.errors import AccessDenied
from hcm_lite.models.domain import AttendanceRecord, AttendanceStatus, Role
from hcm_lite.models.requests import EmployeeSearchFilters, PeriodArgs
from hcm_lite.services.metrics_service import MetricsService
from tests.conftest import TODAY
from tests.unit.services.conftest import sql_all, sql_one, team_ids

OCT_PTD = (date(2026, 10, 1), date(2026, 10, 25))  # this_month, period to date
OCT_FULL = (date(2026, 10, 1), date(2026, 10, 31))  # leave summaries use the full month


def _rate(present: int, remote: int, records: int, on_leave: int) -> float:
    denominator = records - on_leave
    return round((present + remote) / denominator * 100, 1) if denominator > 0 else 0.0


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def expected_attendance(tmp_path, ids: set[str] | None, start: date, end: date,
                        grace: int = 0) -> dict:
    """Counts, lateness and per-department rollups derived straight from SQL rows."""
    where_ids = ""
    params: list = []
    if ids is not None:
        where_ids = f"AND a.employee_id IN ({','.join('?' for _ in ids)})"
        params = sorted(ids)
    rows = sql_all(
        tmp_path,
        "SELECT a.employee_id, e.department, a.status, a.check_in, a.scheduled_start"
        " FROM attendance a JOIN employees e ON e.id = a.employee_id"
        f" WHERE a.date >= ? AND a.date <= ? {where_ids}",
        (start.isoformat(), end.isoformat(), *params),
    )
    counts = {"present": 0, "remote": 0, "absent": 0, "leave": 0}
    late = 0
    by_dept: dict[str, dict[str, int]] = {}
    for _emp, dept, status, check_in, scheduled in rows:
        counts[status] += 1
        dept_row = by_dept.setdefault(
            dept, {"present": 0, "remote": 0, "absent": 0, "leave": 0, "late": 0})
        dept_row[status] += 1
        is_late = (status in ("present", "remote") and check_in is not None
                   and _mins(check_in) > _mins(scheduled) + grace)
        if is_late:
            late += 1
            dept_row["late"] += 1
    for dept_row in by_dept.values():
        dept_row["records"] = sum(dept_row[s] for s in counts)
    return {"counts": counts, "late": late, "by_department": by_dept}


def expected_working_days(tmp_path, start: date, end: date) -> int:
    from hcm_lite.services.periods import working_days

    holidays = {r[0] for r in sql_all(
        tmp_path, "SELECT date FROM holidays WHERE date >= ? AND date <= ?",
        (start.isoformat(), end.isoformat()))}
    return working_days(start, end, holidays)


async def _add_attendance(sf, records) -> None:
    async with sf() as session, session.begin():
        await AttendanceRepo(session).insert_many(records)


# --------------------------------------------------------------------------- my_profile


async def test_my_profile_self_only_with_manager_name(metrics, make_user, tmp_path):
    user = make_user(Role.EMPLOYEE)
    result = await metrics.my_profile(user)
    assert result.ok and result.error is None
    name, manager_name = sql_all(
        tmp_path, "SELECT e.full_name, m.full_name FROM employees e"
                  " LEFT JOIN employees m ON m.id = e.manager_id WHERE e.id = 'E1001'")[0]
    assert result.data.model_dump() == {
        "employee_id": "E1001", "full_name": name, "department": "Engineering",
        "job_title": "Software Engineer", "manager_name": manager_name,
        "hire_date": date.fromisoformat(
            sql_one(tmp_path, "SELECT hire_date FROM employees WHERE id='E1001'")),
    }
    assert result.source == "hr-db:employees" and result.scope == "self"
    assert result.period is None and result.is_demo is True


async def test_my_profile_returns_each_callers_own_record(metrics, make_user):
    for role, eid in ((Role.MANAGER, "M1002"), (Role.HR_ADMIN, "H1003")):
        result = await metrics.my_profile(make_user(role))
        assert result.ok and result.data.employee_id == eid


# --------------------------------------------------------------------------- headcount


async def test_headcount_employee_denied_and_audited(metrics, make_user, tmp_path):
    with pytest.raises(AccessDenied) as exc:
        await metrics.headcount(make_user(Role.EMPLOYEE))
    assert exc.value.capability == "metrics"
    denials = sql_all(tmp_path, "SELECT action, outcome FROM audit_events")
    assert ("access_denied", "denied") in denials


async def test_headcount_team_equals_sql(metrics, make_user, tmp_path):
    result = await metrics.headcount(make_user(Role.MANAGER))
    ids = team_ids(tmp_path)
    marks = ",".join("?" for _ in ids)
    expected = dict(sql_all(
        tmp_path,
        "SELECT department, COUNT(*) FROM employees WHERE employment_status = 'active'"
        f" AND id IN ({marks}) GROUP BY department", tuple(sorted(ids))))
    assert result.ok and result.data.scope == "team"
    assert result.data.by_department == expected
    assert result.data.total_active == sum(expected.values())
    assert result.data.as_of == TODAY
    assert result.source == "hr-db:employees" and result.is_demo is True


async def test_headcount_all_equals_sql(metrics, make_user, tmp_path):
    result = await metrics.headcount(make_user(Role.HR_ADMIN))
    expected = dict(sql_all(
        tmp_path, "SELECT department, COUNT(*) FROM employees"
                  " WHERE employment_status = 'active' GROUP BY department"))
    assert result.ok and result.data.scope == "all"
    assert result.data.by_department == expected
    assert result.data.total_active == sql_one(
        tmp_path, "SELECT COUNT(*) FROM employees WHERE employment_status = 'active'")


async def test_headcount_department_filter_cannot_widen_scope(metrics, make_user, tmp_path):
    manager = make_user(Role.MANAGER)
    team_total = (await metrics.headcount(manager)).data.total_active
    # M1002's whole team is Engineering: filtering Sales yields nothing, never the org figure.
    sales = await metrics.headcount(manager, department="Sales")
    assert sales.ok and sales.data.total_active == 0 and sales.data.by_department == {}
    engineering = await metrics.headcount(manager, department="Engineering")
    assert engineering.ok and engineering.data.total_active == team_total
    org_engineering = sql_one(
        tmp_path, "SELECT COUNT(*) FROM employees"
                  " WHERE employment_status='active' AND department='Engineering'")
    # The filter can never widen: the manager sees at most their own team, never the org.
    assert team_total <= org_engineering
    assert set(engineering.data.by_department) <= {"Engineering"}
    hr = await metrics.headcount(make_user(Role.HR_ADMIN), department="Engineering")
    assert hr.data.total_active == org_engineering


# --------------------------------------------------------------------------- attendance_summary


async def test_attendance_summary_self_equals_sql(metrics, make_user, tmp_path):
    result = await metrics.attendance_summary(make_user(Role.EMPLOYEE),
                                              PeriodArgs(period="this_month"), today=TODAY)
    exp = expected_attendance(tmp_path, {"E1001"}, *OCT_PTD, grace=0)
    c = exp["counts"]
    assert result.ok and result.scope == "self" and result.source == "hr-db:attendance"
    assert result.period == "this_month" and result.is_demo is True
    d = result.data
    assert (d.period.start_date, d.period.end_date, d.period.label) == (*OCT_PTD, "this_month")
    assert d.records == sum(c.values())
    assert (d.present, d.remote, d.absent, d.on_leave) == (
        c["present"], c["remote"], c["absent"], c["leave"])
    assert d.late == exp["late"]
    assert d.working_days == expected_working_days(tmp_path, *OCT_PTD)
    assert d.attendance_rate == _rate(c["present"], c["remote"], sum(c.values()), c["leave"])
    assert [row.department for row in d.by_department] == ["Engineering"]
    dept = d.by_department[0]
    assert (dept.records, dept.late) == (sum(c.values()), exp["late"])


async def test_attendance_summary_team_and_all_equal_sql(metrics, make_user, tmp_path):
    ids = team_ids(tmp_path)
    manager = make_user(Role.MANAGER)
    team = await metrics.attendance_summary(manager, PeriodArgs(period="this_month"),
                                            today=TODAY)
    exp = expected_attendance(tmp_path, ids, *OCT_PTD, grace=0)
    c = exp["counts"]
    assert team.ok and team.scope == "team"
    assert team.data.records == sum(c.values()) and team.data.late == exp["late"]
    assert {row.department: row.records for row in team.data.by_department} == {
        dept: row["records"] for dept, row in exp["by_department"].items()}

    hr = await metrics.attendance_summary(make_user(Role.HR_ADMIN),
                                          PeriodArgs(period="this_month"), today=TODAY)
    exp_all = expected_attendance(tmp_path, None, *OCT_PTD, grace=0)
    assert hr.ok and hr.scope == "all"
    assert hr.data.records == sum(exp_all["counts"].values())
    assert hr.data.late == exp_all["late"]
    assert len(hr.data.by_department) == len(exp_all["by_department"])


async def test_attendance_summary_empty_period_no_data(metrics, make_user):
    result = await metrics.attendance_summary(make_user(Role.HR_ADMIN),
                                              PeriodArgs(period="2026-12"), today=TODAY)
    assert not result.ok and result.error.code == "no_data"
    assert result.source == "hr-db:attendance" and result.period == "2026-12"
    assert result.scope == "all" and result.data is None


# --------------------------------------------------------------------------- late_comers


async def test_late_comers_employee_denied(metrics, make_user):
    with pytest.raises(AccessDenied):
        await metrics.late_comers(make_user(Role.EMPLOYEE), PeriodArgs(period="today"),
                                  today=TODAY)


async def test_late_comers_grace_0_and_10(make_metrics, make_user, sf, tmp_path):
    teammate = sql_one(
        tmp_path, "SELECT id FROM employees WHERE manager_id='M1002' AND id != 'E1001'"
                  " AND employment_status='active' ORDER BY id LIMIT 1")
    day = date(2026, 10, 26)  # Monday, past the seeded attendance window
    records = [
        AttendanceRecord(employee_id="E1001", date=day, status=AttendanceStatus.PRESENT,
                         check_in="09:12", scheduled_start="09:00", is_demo=False),
        AttendanceRecord(employee_id=teammate, date=day, status=AttendanceStatus.PRESENT,
                         check_in="09:05", scheduled_start="09:00", is_demo=False),
        AttendanceRecord(employee_id="E1001", date=date(2026, 10, 27),
                         status=AttendanceStatus.REMOTE,  # on time: never late at any grace
                         check_in="08:55", scheduled_start="09:00", is_demo=False),
        AttendanceRecord(employee_id="H1003", date=day, status=AttendanceStatus.PRESENT,
                         check_in="09:20", scheduled_start="09:00", is_demo=False),
    ]
    await _add_attendance(sf, records)
    rng = PeriodArgs(start_date=day, end_date=date(2026, 10, 27))

    grace0 = make_metrics(late_grace_minutes=0)
    team = await grace0.late_comers(make_user(Role.MANAGER), rng, today=TODAY)
    assert team.ok and team.scope == "team" and team.source == "hr-db:attendance"
    assert team.data.count == 2  # 09:12 (12 late) and 09:05 (5 late); 08:55 on time
    assert [(e.employee_id, e.minutes_late) for e in team.data.entries] == [
        ("E1001", 12), (teammate, 5)]  # sorted by date then employee id
    assert team.data.entries[0].full_name == sql_one(
        tmp_path, "SELECT full_name FROM employees WHERE id='E1001'")
    assert team.data.entries[0].department == "Engineering"
    assert team.data.truncated is False
    assert team.is_demo is False  # propagated from the rows in the period

    grace10 = make_metrics(late_grace_minutes=10)
    team10 = await grace10.late_comers(make_user(Role.MANAGER), rng, today=TODAY)
    assert team10.data.count == 1 and team10.data.entries[0].minutes_late == 12

    # hr_admin sees the whole organisation; the manager never sees out-of-team H1003.
    org = await grace0.late_comers(make_user(Role.HR_ADMIN), rng, today=TODAY)
    assert org.ok and org.scope == "all" and org.data.count == 3
    assert "H1003" in {e.employee_id for e in org.data.entries}
    assert "H1003" not in {e.employee_id for e in team.data.entries}


async def test_late_comers_empty_period_no_data(metrics, make_user):
    # 2026-10-25 is a Sunday: no attendance rows exist for "today".
    result = await metrics.late_comers(make_user(Role.MANAGER), PeriodArgs(period="today"),
                                       today=TODAY)
    assert not result.ok and result.error.code == "no_data"
    assert result.source == "hr-db:attendance" and result.period == "today"
    assert result.scope == "team"


# --------------------------------------------------------------------------- leave_summary


def _expected_leave(tmp_path, ids: set[str] | None, start: date, end: date,
                    status: str | None = None) -> dict:
    where_ids = ""
    params: list = [start.isoformat(), end.isoformat()]
    if ids is not None:
        where_ids = f"AND employee_id IN ({','.join('?' for _ in ids)})"
        params += sorted(ids)
    rows = sql_all(
        tmp_path,
        "SELECT status, leave_type, working_days FROM leave_requests"
        f" WHERE end_date >= ? AND start_date <= ? {where_ids}", tuple(params))
    if status is not None:
        rows = [r for r in rows if r[0] == status]
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    approved_days = 0
    for st, lt, days in rows:
        by_status[st] = by_status.get(st, 0) + 1
        by_type[lt] = by_type.get(lt, 0) + days
        if st == "approved":
            approved_days += days
    return {"by_status": by_status, "by_type": by_type, "total_days_approved": approved_days,
            "count": len(rows)}


async def test_leave_summary_all_full_month_equals_sql(metrics, make_user, tmp_path):
    result = await metrics.leave_summary(make_user(Role.HR_ADMIN),
                                         PeriodArgs(period="this_month"), today=TODAY)
    exp = _expected_leave(tmp_path, None, *OCT_FULL)
    assert result.ok and result.scope == "all" and result.source == "hr-db:leave_requests"
    assert result.period == "this_month" and result.is_demo is True
    d = result.data
    # Exception: leave summaries resolve this_month to the FULL calendar month.
    assert (d.period.start_date, d.period.end_date) == OCT_FULL
    assert d.by_status == exp["by_status"]
    assert d.by_type == exp["by_type"]
    assert d.total_days_approved == exp["total_days_approved"]
    pending_sql = sql_all(
        tmp_path, "SELECT id, employee_id, start_date, end_date, working_days"
                  " FROM leave_requests WHERE status='pending' AND end_date >= '2026-10-01'"
                  " AND start_date <= '2026-10-31' ORDER BY created_at DESC, id DESC LIMIT 25")
    assert len(d.pending) == len(pending_sql)
    assert [(p.reference, p.days, p.start_date, p.end_date) for p in d.pending] == [
        (r[0], r[4], date.fromisoformat(r[2]), date.fromisoformat(r[3])) for r in pending_sql]
    names = dict(sql_all(tmp_path, "SELECT id, full_name FROM employees"))
    assert all(p.employee == names[r[1]] for p, r in zip(d.pending, pending_sql, strict=True))


async def test_leave_summary_status_filter(metrics, make_user, tmp_path):
    result = await metrics.leave_summary(make_user(Role.HR_ADMIN),
                                         PeriodArgs(period="this_month"), status="pending",
                                         today=TODAY)
    exp = _expected_leave(tmp_path, None, *OCT_FULL, status="pending")
    assert result.ok and result.data.by_status == {"pending": exp["count"]}
    assert sum(result.data.by_status.values()) > 0  # the seed guarantees October pending rows


async def test_leave_summary_self_scope_has_no_pending_list(metrics, make_user, tmp_path):
    result = await metrics.leave_summary(make_user(Role.EMPLOYEE),
                                         PeriodArgs(period="this_month"), today=TODAY)
    exp = _expected_leave(tmp_path, {"E1001"}, *OCT_FULL)
    assert result.ok and result.scope == "self"
    assert result.data.by_status == exp["by_status"]
    assert result.data.by_status.get("pending", 0) >= 1  # E1001's guaranteed October request
    assert result.data.pending == []  # the pending list is team/all only


async def test_leave_summary_team_pending_within_scope(metrics, make_user, tmp_path):
    ids = team_ids(tmp_path)
    result = await metrics.leave_summary(make_user(Role.MANAGER),
                                         PeriodArgs(period="this_month"), today=TODAY)
    assert result.ok and result.scope == "team"
    exp = _expected_leave(tmp_path, ids, *OCT_FULL)
    assert result.data.by_status == exp["by_status"]
    assert len(result.data.pending) > 0  # seeded pending rows for M1002's team
    assert {p.reference for p in result.data.pending} <= {
        r[0] for r in sql_all(
            tmp_path, "SELECT id FROM leave_requests WHERE status='pending'"
                      " AND employee_id IN ({})".format(",".join("?" for _ in ids)),
            tuple(sorted(ids)))}


async def test_leave_summary_department_filter_cannot_widen(metrics, make_user, tmp_path):
    manager = make_user(Role.MANAGER)
    sales = await metrics.leave_summary(manager, PeriodArgs(period="this_month"),
                                        department="Sales", today=TODAY)
    assert not sales.ok and sales.error.code == "no_data"  # team is Engineering-only
    engineering = await metrics.leave_summary(manager, PeriodArgs(period="this_month"),
                                              department="Engineering", today=TODAY)
    unfiltered = await metrics.leave_summary(manager, PeriodArgs(period="this_month"),
                                             today=TODAY)
    assert engineering.ok and engineering.data.by_status == unfiltered.data.by_status


async def test_leave_summary_empty_period_no_data(metrics, make_user):
    result = await metrics.leave_summary(make_user(Role.HR_ADMIN),
                                         PeriodArgs(period="2026-07"), today=TODAY)
    assert not result.ok and result.error.code == "no_data"
    assert result.source == "hr-db:leave_requests" and result.period == "2026-07"
    assert result.scope == "all"


# --------------------------------------------------------------------------- payroll_summary


async def test_payroll_denied_for_employee_and_manager(metrics, make_user, tmp_path):
    for role in (Role.EMPLOYEE, Role.MANAGER):
        with pytest.raises(AccessDenied) as exc:
            await metrics.payroll_summary(make_user(role), period="2026-09", today=TODAY)
        assert exc.value.capability == "payroll"
    assert sql_all(tmp_path, "SELECT COUNT(*) FROM audit_events WHERE action='access_denied'")


async def test_payroll_hr_aggregates_equal_sql(metrics, make_user, tmp_path):
    result = await metrics.payroll_summary(make_user(Role.HR_ADMIN), period="2026-09",
                                           today=TODAY)
    rows = sql_all(
        tmp_path, "SELECT department, headcount_paid, gross_total, net_total"
                  " FROM payroll_totals WHERE period='2026-09' ORDER BY department")
    totals = sql_all(
        tmp_path, "SELECT SUM(headcount_paid), SUM(gross_total), SUM(net_total)"
                  " FROM payroll_totals WHERE period='2026-09'")[0]
    assert result.ok and result.scope == "all" and result.source == "hr-db:payroll_totals"
    assert result.period == "2026-09" and result.is_demo is True
    d = result.data
    assert d.period == "2026-09" and d.currency == "USD"
    assert [(r.department, r.headcount_paid, str(r.gross_total), str(r.net_total))
            for r in d.by_department] == [(r[0], r[1], f"{r[2]:.2f}", f"{r[3]:.2f}")
                                          for r in rows]
    assert (d.headcount_paid, str(d.gross_total), str(d.net_total)) == (
        totals[0], f"{totals[1]:.2f}", f"{totals[2]:.2f}")
    # Aggregates only: the payload has no per-employee pay field anywhere.
    assert set(d.model_dump()) == {"period", "currency", "gross_total", "net_total",
                                   "headcount_paid", "by_department"}


async def test_payroll_default_is_last_month(metrics, make_user):
    result = await metrics.payroll_summary(make_user(Role.HR_ADMIN), today=TODAY)
    assert result.ok and result.data.period == "2026-09"


async def test_payroll_department_filter(metrics, make_user, tmp_path):
    result = await metrics.payroll_summary(make_user(Role.HR_ADMIN), period="2026-09",
                                           department="Engineering", today=TODAY)
    row = sql_all(
        tmp_path, "SELECT headcount_paid, gross_total FROM payroll_totals"
                  " WHERE period='2026-09' AND department='Engineering'")[0]
    assert result.ok and [r.department for r in result.data.by_department] == ["Engineering"]
    assert result.data.headcount_paid == row[0] and str(result.data.gross_total) == f"{row[1]:.2f}"


async def test_payroll_empty_period_no_data(metrics, make_user):
    result = await metrics.payroll_summary(make_user(Role.HR_ADMIN), period="2025-01",
                                           today=TODAY)
    assert not result.ok and result.error.code == "no_data"
    assert result.source == "hr-db:payroll_totals" and result.period == "2025-01"
    assert result.scope == "all"


# --------------------------------------------------------------------------- search_employees


async def test_search_employees_denied_for_employee(metrics, make_user):
    with pytest.raises(AccessDenied):
        await metrics.search_employees(make_user(Role.EMPLOYEE),
                                       EmployeeSearchFilters(name="demo"))


async def test_search_employees_manager_scope_only(metrics, make_user, tmp_path):
    outside = sql_one(tmp_path, "SELECT full_name FROM employees WHERE id='H1003'")
    manager = make_user(Role.MANAGER)
    result = await metrics.search_employees(manager, EmployeeSearchFilters(name=outside))
    assert result.ok and result.scope == "team" and result.data.count == 0
    teammate = sql_one(
        tmp_path, "SELECT full_name FROM employees WHERE manager_id='M1002'"
                  " AND employment_status='active' ORDER BY id LIMIT 1")
    hit = await metrics.search_employees(manager, EmployeeSearchFilters(name=teammate))
    assert hit.ok and hit.data.count >= 1
    ids = team_ids(tmp_path)
    assert {e.employee_id for e in hit.data.employees} <= ids
    hr = await metrics.search_employees(make_user(Role.HR_ADMIN),
                                        EmployeeSearchFilters(name=outside))
    assert hr.ok and hr.scope == "all" and hr.data.count >= 1
    assert result.source == "hr-db:employees" and hit.is_demo is True
