"""One-shot generator for the demo HR documents (US2 T063). Run from the repo root:

    .venv/Scripts/python scripts/make_demo_docs.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path("data/demo/documents/policies")


def write_md(name: str, title: str, scope: str, body: str, version: str = "1.0") -> None:
    fm = (
        "---\n"
        f"title: {title}\n"
        f"version: {version}\n"
        "doc_type: policy\n"
        f"access_scope: {scope}\n"
        "demo: true\n"
        "---\n\n"
    )
    (ROOT / f"{name}.md").write_text(fm + body, encoding="utf-8")


DOCS: dict[str, str] = {}

DOCS["annual-leave"] = """DEMO — fictional company; all data is synthetic.

# Annual leave entitlement

Every full-time employee is entitled to **20 paid annual leave days** per calendar year. Part-time employees receive leave pro rata to their contracted hours.

New joiners accrue 1.67 days per completed month of service; from the second year the full entitlement is available on 1 January.

# Carrying leave over

Up to **5 unused days** may be carried into the first quarter of the next year. Carried days expire on 31 March.

# Booking rules

Annual leave must be requested at least **10 working days** before the start date and cannot exceed **15 consecutive working days** in one request.

Leave overlapping a public holiday is not deducted for the holiday day itself.

# Approval

The employee's manager approves or declines within **3 working days**. If no decision is recorded in that window the request is escalated to HR.
"""

DOCS["sick-leave"] = """DEMO — fictional company; all data is synthetic.

# Sick leave entitlement

Employees receive **10 paid sick days** per calendar year. Sick leave is not carried over and does not convert to annual leave.

# Notification

Notify your manager **before 09:30** on the first day of absence, or as soon as practicable, by phone or chat message.

# Medical certificates

A medical certificate is required for any absence **longer than 3 consecutive working days**, submitted to HR within 5 working days of returning.

# Extended illness

Absences beyond the paid entitlement, or beyond 30 consecutive days, move to long-term sick leave and are handled case by case with HR and the company's insurer.
"""

DOCS["casual-and-unpaid-leave"] = """DEMO — fictional company; all data is synthetic.

# Casual leave

Employees have **5 paid casual leave days** per year for short-notice personal matters (family care, moving house, appointments that cannot be scheduled outside work hours). Casual leave is requested at least **48 hours** in advance where possible.

# Unpaid leave

Unpaid leave may be granted for sabbaticals, study, or extended personal reasons. Conditions:

- Minimum length: 5 working days; maximum: 90 days per calendar year.
- Manager and HR approval both required; requests are considered against team coverage.
- Unpaid leave does not accrue annual entitlement and pauses leave accrual for its duration.

# Deduction

Unpaid days are deducted from the monthly salary in the month they occur.
"""

DOCS["attendance-and-punctuality"] = """DEMO — fictional company; all data is synthetic.

# Working hours

The standard work day runs **09:00 to 17:30**, Monday to Friday, including a 30-minute unpaid lunch break.

# Check-in

Employees record attendance through the HCM Lite check-in feature. The check-in window opens at 08:30.

# Late arrival

Arrivals **after 09:10** (a grace period of 10 minutes) are recorded as late. Repeated lateness — more than 4 late arrivals in a calendar month — is discussed with the manager.

# Early departure and absence

Leaving earlier than 17:30 or being absent requires manager approval recorded in advance. Unnotified absence is followed up by the manager on the same day.
"""

DOCS["remote-work"] = """DEMO — fictional company; all data is synthetic.

# Hybrid model

The company operates a **hybrid model**: employees work from the office at least **2 days per week** (core days Tuesday and Wednesday) and may work remotely on the remaining days, by agreement with their manager.

# Eligibility

Remote work is open to employees after **3 months** of service and depends on role requirements. Roles that require physical presence (front desk, facilities) are excluded.

# Expectations while remote

- Be reachable during working hours on the company chat.
- Attend scheduled meetings with camera on when bandwidth allows.
- Record attendance status as "remote" on remote days.

# Working from another country

Working from outside the country of employment for more than 20 working days per year requires prior HR and tax approval.
"""

DOCS["code-of-conduct"] = """DEMO — fictional company; all data is synthetic.

# Core principles

Employees act with integrity, respect, and professionalism toward colleagues, candidates, and customers.

# Respectful workplace

Discrimination, harassment, or bullying of any kind is prohibited. Reports can be raised with any manager or HR confidentially; retaliation against a reporter is itself a violation.

# Company assets and data

- Company devices and accounts are for business use; personal use must not create risk.
- Employee and payroll data may be accessed only through authorized systems and only within the permissions of your role.
- Confidential information must not be shared outside its intended audience, during and after employment.

# Conflicts of interest

Outside employment, board seats, or financial interests that conflict with the company's business must be declared to HR in writing.

# Breaches

Breaches are investigated by HR. Sanctions range from a documented warning to termination, depending on severity.
"""

DOCS["public-holidays-2026"] = """DEMO — fictional company; all data is synthetic.

# Company public holidays 2026

The company observes the following 11 paid public holidays in 2026:

- Thursday 1 January — New Year's Day
- Friday 3 April — Good Friday
- Monday 6 April — Easter Monday
- Monday 4 May — Labour Day (observed)
- Thursday 14 May — Ascension Day
- Monday 25 May — Spring Holiday
- Monday 8 June — Whit Monday
- Wednesday 24 June — Midsummer Eve
- Monday 10 August — Summer Holiday
- Thursday 24 December — Christmas Eve
- Friday 25 December — Christmas Day

# Falling on a weekend

When a holiday falls on a Saturday or Sunday, the following Monday is observed as the holiday.

# Working on a holiday

Work on a public holiday requires prior manager approval and is compensated with time off in lieu within 90 days.
"""

DOCS["manager-guide-leave-approvals"] = """DEMO — fictional company; all data is synthetic.

# Your responsibilities as an approver

You are the first approver for annual, casual, and sick leave requests of your direct reports. Decide within **3 working days**; undecided requests escalate to HR automatically.

# Checking coverage before approving

Before approving, confirm that approving will not leave the team below minimum coverage:

- At least 60% of the team present on any given day.
- No more than one direct report on leave on the same day for teams of five or fewer.
- Peak periods (month-end closing, release weeks) are staffed; ask for a handover note for absences longer than 5 days.

# When to decline or ask for changes

Decline or ask to reschedule when coverage rules fail, when the request violates policy (for example more than 15 consecutive annual leave days, or fewer than 10 days notice without a stated reason), or during a documented blackout period. Always give a reason in the response.

# Sick leave and sensitive reasons

Sick leave and sensitive personal reasons do not require detailed justification to you; a certificate beyond 3 days goes to HR, not to the manager.
"""

DOCS["payroll-processing"] = """DEMO — fictional company; all data is synthetic.

# Payroll calendar

Payroll runs monthly. The **cutoff is the 25th** of the month; payments reach accounts on the **last working day** of the month.

# Inputs and checks

HR administrators verify before each run:

- New joiners and leavers are entered with correct start/end dates and bank details.
- Approved leave, unpaid days, and overtime from HCM Lite flow into the run; unpaid leave is deducted in the month it occurs.
- Variable payments (bonuses, allowances) are entered against the right cost center.

# Review and release

The draft register is reviewed by a second HR administrator before release. The review confirms gross-to-net totals per department against the previous month and explains any variance above 5%.

# Confidentiality

Payroll data is strictly confidential. Per-employee pay figures may be shared only with the employee, their HR administrators, and statutory authorities. Aggregate totals are the only figures used in dashboards and reports.

# Corrections

Overpayments are recovered in the following month unless the employee agrees otherwise in writing; underpayments are corrected with an unscheduled payment within 5 working days.
"""

TITLES = {
    "annual-leave": "Annual Leave Policy",
    "sick-leave": "Sick Leave Policy",
    "casual-and-unpaid-leave": "Casual and Unpaid Leave",
    "attendance-and-punctuality": "Attendance and Punctuality",
    "remote-work": "Remote Work Policy",
    "code-of-conduct": "Code of Conduct",
    "public-holidays-2026": "Public Holidays 2026",
    "manager-guide-leave-approvals": "Manager Guide: Leave Approvals",
    "payroll-processing": "Payroll Processing",
}
SCOPES = {
    "manager-guide-leave-approvals": "managers",
    "payroll-processing": "hr_admin",
}


def make_pdf(path: Path, lines: list[str]) -> None:
    """Minimal valid single-page PDF with Helvetica text (no external deps)."""
    def esc(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content_parts = ["BT", "/F1 11 Tf", "50 790 Td", "15 TL"]
    for line in lines:
        content_parts.append(f"({esc(line)}) Tj T*")
    content_parts.append("ET")
    stream = "\n".join(content_parts).encode("latin-1", "replace")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")                                   # 1
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")                          # 2
    objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                   b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")           # 3
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")              # 4
    objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")  # 5

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref_at).encode()
            + b"\n%%EOF\n")
    path.write_bytes(bytes(out))


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for name, body in DOCS.items():
        write_md(name, TITLES[name], SCOPES.get(name, "all_employees"), body)
    make_pdf(ROOT / "employee-handbook-summary.pdf", [
        "---",
        "title: Employee Handbook Summary",
        "version: 1.0",
        "doc_type: policy",
        "access_scope: all_employees",
        "demo: true",
        "---",
        "DEMO - fictional company; all data is synthetic.",
        "Employee Handbook Summary (extract)",
        "",
        "Working time: 09:00-17:30 Mon-Fri, 30 min unpaid lunch. Check in via HCM Lite.",
        "Hybrid: at least 2 office days per week (core days Tue, Wed) by manager agreement.",
        "Annual leave: 20 days/yr, request 10 working days ahead, max 15 consecutive days;",
        "carry over max 5 days until 31 March.",
        "Sick leave: 10 days/yr, notify manager before 09:30, certificate beyond 3 days.",
        "Casual leave: 5 days/yr for short-notice personal matters.",
        "Late: after 09:10 (10-minute grace). More than 4 late arrivals a month triggers",
        "a manager conversation.",
        "Leave approvals: managers decide within 3 working days; silence escalates to HR.",
        "Questions: ask HR via the assistant or hr-demo@example.com.",
    ])
    for p in sorted(ROOT.iterdir()):
        print(f"{p.name:45s} {p.stat().st_size:>7d} bytes")


if __name__ == "__main__":
    main()
