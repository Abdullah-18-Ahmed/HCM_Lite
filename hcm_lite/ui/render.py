"""Dashboard markdown rendering (T053, contracts/ui.md, FR-011).

Pure markdown generation, independent of Chainlit: ``app.py`` puts the returned text into the
``cl.ElementSidebar``. Tables always state their period (or as-of date) and the demo label
appears whenever the underlying rows are demo rows (US1 scenario 7).
"""

from __future__ import annotations

from typing import Any

from hcm_lite.models.results import (
    AttendanceSummary,
    DashboardData,
    EmployeeSearchResult,
    HeadcountResult,
    LateComersResult,
    LeaveBalanceResult,
    LeaveRequestList,
    LeaveSummary,
    PayrollSummary,
    ProfileResult,
    ToolResult,
)

__all__ = ["render_dashboard", "render_error"]

_NO_DATA = "No records for this period."

_TITLES = {
    "profile": "My profile",
    "my_attendance": "My attendance — this month",
    "my_balances": "My leave balances",
    "my_leave_requests": "My leave requests",
    "team_headcount": "Team headcount",
    "team_attendance": "Team attendance — this month",
    "team_late_today": "Team late arrivals — today",
    "team_pending_leave": "Team pending leave — this month",
    "headcount": "Workforce headcount",
    "org_attendance": "Organization attendance — this month",
    "leave_summary": "Leave summary — this month",
    "payroll_last_month": "Payroll — last month",
}

_ROLE_LABELS = {"employee": "Employee", "manager": "Manager", "hr_admin": "HR Administrator"}


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _title(name: str) -> str:
    return _TITLES.get(name, name.replace("_", " ").title())


def _num(value: Any) -> str:
    return f"{value:.1f}" if isinstance(value, float) else str(value)


# --------------------------------------------------------------------------- payload tables


def _profile(data: ProfileResult) -> list[str]:
    d = data.model_dump(mode="json")
    return _table(
        ["Field", "Value"],
        [["Full name", d["full_name"]], ["Department", d["department"]],
         ["Job title", d["job_title"]], ["Manager", d["manager_name"] or "—"],
         ["Hire date", d["hire_date"]], ["Employee ID", d["employee_id"]]])


def _attendance(data: AttendanceSummary) -> list[str]:
    p = data.period
    lines = [f"**Period:** {p.label} ({p.start_date} to {p.end_date})"]
    lines += _table(
        ["Metric", "Value"],
        [["Working days", str(data.working_days)], ["Records", str(data.records)],
         ["Present", str(data.present)], ["Remote", str(data.remote)],
         ["Absent", str(data.absent)], ["On leave", str(data.on_leave)],
         ["Late", str(data.late)], ["Attendance rate %", _num(data.attendance_rate)]])
    lines += _table(
        ["Department", "Records", "Present", "Remote", "Absent", "On leave", "Late", "Rate %"],
        [[row.department, str(row.records), str(row.present), str(row.remote), str(row.absent),
          str(row.on_leave), str(row.late), _num(row.attendance_rate)]
         for row in data.by_department])
    return lines


def _late_comers(data: LateComersResult) -> list[str]:
    p = data.period
    lines = [f"**Period:** {p.label} ({p.start_date} to {p.end_date})",
             f"Late arrivals: **{data.count}**"]
    lines += _table(
        ["Employee", "Department", "Date", "Check-in", "Minutes late"],
        [[e.full_name, e.department, str(e.date), e.check_in, str(e.minutes_late)]
         for e in data.entries])
    if data.truncated:
        lines.append(f"Showing the first {len(data.entries)} of {data.count}.")
    return lines


def _leave_summary(data: LeaveSummary) -> list[str]:
    p = data.period
    lines = [f"**Period:** {p.label} ({p.start_date} to {p.end_date})"]
    lines += _table(["Status", "Requests"],
                    [[status, str(count)] for status, count in sorted(data.by_status.items())])
    lines += _table(["Leave type", "Days"],
                    [[leave_type, str(days)] for leave_type, days in data.by_type.items()])
    lines.append(f"Approved days: **{data.total_days_approved}**")
    if data.pending:
        lines += _table(
            ["Reference", "Employee", "Start", "End", "Days"],
            [[p.reference, p.employee, str(p.start_date), str(p.end_date), str(p.days)]
             for p in data.pending])
    return lines


def _balance(data: LeaveBalanceResult) -> list[str]:
    lines = [f"**As of:** {data.as_of} (year {data.year})"]

    def money(value: Any) -> str:
        return f"{value:.2f}"

    lines += _table(
        ["Type", "Entitled", "Used", "Pending", "Remaining"],
        [[b.leave_type, money(b.entitled), money(b.used), money(b.pending), money(b.remaining)]
         for b in data.balances])
    return lines


def _requests(data: LeaveRequestList) -> list[str]:
    return _table(
        ["Reference", "Type", "Start", "End", "Days", "Status"],
        [[r.reference, str(r.leave_type), str(r.start_date), str(r.end_date),
          str(r.working_days), str(r.status)] for r in data.requests])


def _headcount(data: HeadcountResult) -> list[str]:
    lines = [f"**As of:** {data.as_of} (scope: {data.scope})"]
    lines += _table(
        ["Department", "Active"],
        [[department, str(count)] for department, count in data.by_department.items()]
        + [["**Total**", f"**{data.total_active}**"]])
    return lines


def _payroll(data: PayrollSummary) -> list[str]:
    lines = [f"**Period:** {data.period} (currency {data.currency})"]
    lines += _table(
        ["Department", "Headcount paid", "Gross", "Net"],
        [[row.department, str(row.headcount_paid), str(row.gross_total), str(row.net_total)]
         for row in data.by_department]
        + [["**Total**", f"**{data.headcount_paid}**", f"**{data.gross_total}**",
            f"**{data.net_total}**"]])
    return lines


def _search(data: EmployeeSearchResult) -> list[str]:
    return _table(
        ["Employee", "Department", "Title", "Status"],
        [[e.full_name, e.department, e.job_title, str(e.employment_status)]
         for e in data.employees])


_RENDERERS = {
    ProfileResult: _profile,
    AttendanceSummary: _attendance,
    LateComersResult: _late_comers,
    LeaveSummary: _leave_summary,
    LeaveBalanceResult: _balance,
    LeaveRequestList: _requests,
    HeadcountResult: _headcount,
    PayrollSummary: _payroll,
    EmployeeSearchResult: _search,
}


def _render_result(result: ToolResult[Any]) -> list[str]:
    if not result.ok:
        if result.error is not None and result.error.code == "no_data":
            return [_NO_DATA]
        return ["Unavailable right now."]
    for payload_type, renderer in _RENDERERS.items():
        if isinstance(result.data, payload_type):
            return renderer(result.data)
    return _table(["Field", "Value"],
                  [[k, _num(v)] for k, v in result.data.model_dump(mode="json").items()
                   if not isinstance(v, (dict, list))])


def render_dashboard(data: DashboardData) -> str:
    """Markdown for one role's dashboard: titled sections, tables, periods, demo label."""
    lines = [f"## {_ROLE_LABELS.get(str(data.role), str(data.role))} dashboard", ""]
    if any(result.is_demo for result in data.sections.values()):
        lines += ["**Demo data** — fictional demonstration records.", ""]
    for name, result in data.sections.items():
        lines += [f"### {_title(name)}", *_render_result(result), ""]
    if data.withheld:
        lines.append("Withheld (your role does not permit these figures): "
                     + ", ".join(_title(n) for n in data.withheld))
    if data.unavailable:
        lines.append("Unavailable right now: " + ", ".join(_title(n) for n in data.unavailable))
    return "\n".join(lines).rstrip() + "\n"


def render_error(message: str) -> str:
    """A one-line, safe error note (never a traceback or internal detail)."""
    return f"> {message}\n"


def render_sources(citations: list[Any]) -> str:
    """Markdown source list for a turn's citations (US2 T074)."""
    if not citations:
        return ""
    lines = ["**Sources**"]
    for citation in citations:
        label = getattr(citation, "label", None) or f"[{citation.n}] {citation.title}"
        lines.append(f"- {label}")
    return "\n".join(lines) + "\n"


def render_draft(draft: Any) -> str:
    """A leave DRAFT summary — clearly labelled as not submitted (US5 T101)."""
    money = getattr(draft, "balance_remaining", None)
    remaining = f" (remaining after this leave: {money})" if money is not None else ""
    dates = f"{draft.start_date.isoformat()} → {draft.end_date.isoformat()}" \
        if draft.start_date and draft.end_date else "dates incomplete"
    days = f", {draft.working_days} working day(s)" if draft.working_days else ""
    lines = [
        "**DRAFT — not submitted**",
        "",
        f"- Type: **{getattr(draft.leave_type, 'value', draft.leave_type) or '?'}**",
        f"- Dates: {dates}{days}{remaining}",
    ]
    if draft.reason:
        lines.append(f"- Reason: {draft.reason}")
    for warning in draft.warnings:
        lines.append(f"- ⚠ {warning}")
    return "\n".join(lines) + "\n"
