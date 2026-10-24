"""Demo data seed (research D-13, constitution Art. IX.1.6). DEMO — fictional data only.

``build_demo_data(today)`` is pure and deterministic (seeded RNG): 6 departments, 60 employees
with a manager hierarchy, weekday attendance from the first day of the month two months before
``today`` up to the last working day <= ``today``, leave requests (including pending ones in the
current month and at least one later in the month), balances, payroll totals per month and
department, and holidays. ``run_seed`` writes it through the repositories, with three demo
accounts whose passwords are generated with ``secrets`` on every run and returned once for
printing (they are never stored in code or logs).

Every row has ``is_demo = 1``. Seeding refuses unless the DB is at head, refuses when non-demo
rows exist (unless ``force``), and refuses when demo rows exist (unless ``reset``, which first
deletes only ``is_demo = 1`` rows).
"""

from __future__ import annotations

import calendar
import random
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncEngine

from hcm_lite.db.engine import OUT_OF_DATE_MESSAGE, assert_at_head, session_factory
from hcm_lite.db.repositories import (
    AdminRepo,
    AttendanceRepo,
    EmployeeRepo,
    HolidayRepo,
    LeaveRepo,
    PayrollRepo,
    UserRepo,
)
from hcm_lite.errors import ConfigurationError, HCMError
from hcm_lite.models.domain import (
    AttendanceRecord,
    AttendanceStatus,
    DepartmentRecord,
    EmployeeRecord,
    EmploymentStatus,
    HolidayRecord,
    LeaveBalanceRecord,
    LeaveRequestRecord,
    LeaveSource,
    LeaveStatus,
    LeaveType,
    LeaveTypeRecord,
    PayrollTotalRecord,
    Role,
    UserRecord,
)
from hcm_lite.services.passwords import hash_password

__all__ = [
    "DEFAULT_SEED", "DEMO_USERNAMES", "DemoCredential", "DemoData", "SeedRefused", "SeedReport",
    "build_demo_data", "last_working_day", "run_seed",
]

DEFAULT_SEED = 20261025
DEMO_USERNAMES = ("employee", "manager", "hr_admin")
SCHEDULED_START = "09:00"
CURRENCY = "USD"

DEPARTMENTS = ("Engineering", "Sales", "Marketing", "Finance", "Human Resources", "Operations")
JOB_TITLES = {
    "Engineering": ("Software Engineer", "QA Engineer", "DevOps Engineer"),
    "Sales": ("Account Executive", "Sales Representative"),
    "Marketing": ("Marketing Specialist", "Content Writer"),
    "Finance": ("Accountant", "Financial Analyst"),
    "Human Resources": ("HR Generalist", "Recruiter"),
    "Operations": ("Operations Analyst", "Office Coordinator"),
}
MONTHLY_GROSS = {  # fictional average gross pay per head
    "Engineering": 6200, "Sales": 4800, "Marketing": 4500, "Finance": 5200,
    "Human Resources": 4300, "Operations": 4000,
}
#: Fictional demo calendar (month, day, name), repeated for each year in the window.
HOLIDAYS = ((1, 1, "New Year's Day"), (5, 1, "Labour Day"), (8, 14, "Independence Day"),
            (12, 25, "Year-End Holiday"))
ENTITLEMENTS = {LeaveType.ANNUAL: 20, LeaveType.SICK: 10, LeaveType.CASUAL: 6}
LEAVE_LABELS = {LeaveType.ANNUAL: "Annual leave", LeaveType.SICK: "Sick leave",
                LeaveType.CASUAL: "Casual leave", LeaveType.UNPAID: "Unpaid leave",
                LeaveType.OTHER: "Other leave"}
REASONS = ("Family event (demo)", "Personal errand (demo)", "Medical appointment (demo)",
           "Short trip (demo)", "Rest day (demo)")
FIRST_NAMES = ("Ayla", "Bilal", "Chen", "Dana", "Elif", "Farah", "Gabe", "Hana", "Imran", "Jonas",
               "Kira", "Leo", "Mina", "Noor", "Omar", "Priya", "Quinn", "Rosa", "Sami", "Tara",
               "Umar", "Vera", "Wes", "Yara", "Zane")
LAST_NAMES = ("Demo", "Sample", "Example", "Testwell", "Placeholder", "Fictive", "Mockford",
              "Pretend", "Invented", "Madeup", "Notreal", "Stand-in")
_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_DEMO_USERS = (  # (user id, username, role, employee id)
    ("U0001", "employee", Role.EMPLOYEE, "E1001"),
    ("U0002", "manager", Role.MANAGER, "M1002"),
    ("U0003", "hr_admin", Role.HR_ADMIN, "H1003"),
)


class SeedRefused(HCMError):
    """The seed would be unsafe; the CLI exits with code 2."""

    category = "refused"


@dataclass(frozen=True)
class DemoCredential:
    username: str
    role: Role
    employee_id: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class SeedReport:
    counts: dict[str, int]
    credentials: list[DemoCredential]
    attendance_end: date


@dataclass(frozen=True)
class DemoData:
    departments: list[DepartmentRecord]
    leave_types: list[LeaveTypeRecord]
    holidays: list[HolidayRecord]
    employees: list[EmployeeRecord]  # managers before their reports
    leave_requests: list[LeaveRequestRecord]
    attendance: list[AttendanceRecord]
    balances: list[LeaveBalanceRecord]
    payroll: list[PayrollTotalRecord]
    attendance_end: date


# --------------------------------------------------------------------------- calendar helpers


def _is_working(day: date, holidays: set[date]) -> bool:
    return day.weekday() < 5 and day not in holidays


def last_working_day(today: date, holidays: set[date] | frozenset[date]) -> date:
    """The last weekday that is not a holiday, on or before ``today``."""
    day = today
    while not _is_working(day, set(holidays)):
        day -= timedelta(days=1)
    return day


def _working_dates(start: date, end: date, holidays: set[date]) -> list[date]:
    days, day = [], start
    while day <= end:
        if _is_working(day, holidays):
            days.append(day)
        day += timedelta(days=1)
    return days


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def _month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


# --------------------------------------------------------------------------- generation


def _employees(rng: random.Random, window_start: date) -> list[EmployeeRecord]:
    names = [f"{f} {last}" for f in FIRST_NAMES for last in LAST_NAMES]
    rng.shuffle(names)
    name_iter = iter(names)

    def hire() -> date:
        return date(2018, 1, 1) + timedelta(days=rng.randint(0, (window_start - date(2018, 1, 1)
                                                                 ).days - 30))

    def emp(eid: str, dept: str, title: str, manager: str | None) -> EmployeeRecord:
        return EmployeeRecord(
            id=eid, full_name=next(name_iter), department=dept, job_title=title,
            employment_status=EmploymentStatus.ACTIVE, hire_date=hire(), manager_id=manager,
            is_demo=True,
        )

    managers = {"Engineering": "M1002"}
    for number, dept in enumerate(d for d in DEPARTMENTS if d != "Engineering"):
        managers[dept] = f"M{1004 + number}"
    result = [emp(managers[d], d, f"{d} Manager", None) for d in DEPARTMENTS]
    result.append(emp("E1001", "Engineering", "Software Engineer", "M1002"))
    result.append(emp("H1003", "Human Resources", "HR Administrator", managers["Human Resources"]))
    next_id = 1009
    staff: list[EmployeeRecord] = []
    for dept in DEPARTMENTS:
        fixed = 2 if dept in ("Engineering", "Human Resources") else 1
        for _ in range(10 - fixed):
            staff.append(emp(f"E{next_id}", dept, rng.choice(JOB_TITLES[dept]), managers[dept]))
            next_id += 1
    inactive = set(rng.sample([e.id for e in staff], 2))
    staff = [e.model_copy(update={"employment_status": EmploymentStatus.INACTIVE})
             if e.id in inactive else e for e in staff]
    return result + staff


def _pick_type(rng: random.Random) -> LeaveType:
    return rng.choices([LeaveType.ANNUAL, LeaveType.SICK, LeaveType.CASUAL, LeaveType.UNPAID],
                       weights=[50, 25, 20, 5])[0]


def _past_status(rng: random.Random) -> LeaveStatus:
    return rng.choices([LeaveStatus.APPROVED, LeaveStatus.PENDING, LeaveStatus.REJECTED,
                        LeaveStatus.CANCELLED], weights=[60, 20, 15, 5])[0]


def build_demo_data(today: date, *, rng_seed: int = DEFAULT_SEED) -> DemoData:
    rng = random.Random(rng_seed)
    window_start = _add_months(today.replace(day=1), -2)
    month_start = today.replace(day=1)
    month_end = _month_end(today)
    next_month_end = _month_end(_add_months(today, 1))

    holidays = [
        HolidayRecord(date=date(year, m, d), name=name, is_demo=True)
        for year in range(window_start.year, next_month_end.year + 1)
        for m, d, name in HOLIDAYS
    ]
    holiday_dates = {h.date for h in holidays}
    attendance_end = last_working_day(today, holiday_dates)

    employees = _employees(rng, window_start)
    active = [e for e in employees if e.employment_status == EmploymentStatus.ACTIVE]
    user_of = {eid: uid for uid, _, _, eid in _DEMO_USERS}
    hr_user = _DEMO_USERS[2][0]

    # ----- leave requests (no overlaps per employee)
    used_refs: set[str] = set()
    taken: dict[str, set[date]] = {e.id: set() for e in employees}
    requests: list[LeaveRequestRecord] = []

    def reference(created: date) -> str:
        while True:
            ref = f"LR-{created:%Y%m%d}-" + "".join(rng.choice(_REF_ALPHABET) for _ in range(4))
            if ref not in used_refs:
                used_refs.add(ref)
                return ref

    def add_request(eid: str, days: list[date], status: LeaveStatus,
                    leave_type: LeaveType) -> bool:
        if not days or taken[eid] & set(days):
            return False
        taken[eid].update(days)
        start, end = days[0], days[-1]
        created_day = min(start - timedelta(days=rng.randint(3, 14)), today - timedelta(days=1))
        created_at = datetime.combine(created_day, time(9, 0), UTC) + timedelta(
            minutes=rng.randint(0, 480))
        requests.append(LeaveRequestRecord(
            id=reference(created_day), employee_id=eid, leave_type=leave_type, start_date=start,
            end_date=end, working_days=len(days), reason=rng.choice(REASONS), status=status,
            source=LeaveSource.SEED, idempotency_key=None,
            created_by=user_of.get(eid, hr_user), created_at=created_at, is_demo=True,
        ))
        return True

    past_month = _working_dates(_add_months(month_start, -1),
                                _month_end(_add_months(month_start, -1)), holiday_dates)
    future_in_month = _working_dates(today + timedelta(days=1), month_end, holiday_dates)
    if not future_in_month:  # today is the last working day: use next month's first days
        future_in_month = _working_dates(month_end + timedelta(days=1), next_month_end,
                                         holiday_dates)
    this_month_past = _working_dates(month_start, attendance_end, holiday_dates)

    # guaranteed rows for the demo accounts and the manager's team
    add_request("E1001", past_month[3:5], LeaveStatus.APPROVED, LeaveType.ANNUAL)
    add_request("E1001", future_in_month[:2], LeaveStatus.PENDING, LeaveType.ANNUAL)
    team = [e.id for e in active if e.manager_id == "M1002" and e.id != "E1001"]
    add_request(team[0], (this_month_past or future_in_month)[-1:], LeaveStatus.PENDING,
                LeaveType.SICK)
    add_request(team[1], future_in_month[-1:], LeaveStatus.PENDING, LeaveType.CASUAL)
    add_request("M1002", past_month[8:9], LeaveStatus.APPROVED, LeaveType.CASUAL)
    add_request("H1003", this_month_past[:1] or past_month[:1], LeaveStatus.REJECTED,
                LeaveType.ANNUAL)

    window_days = _working_dates(window_start, month_end, holiday_dates)
    for e in active:
        for _ in range(rng.randint(0, 3)):
            i = rng.randrange(len(window_days))
            days = window_days[i:i + rng.randint(1, 3)]
            status = LeaveStatus.PENDING if days[0] > today else _past_status(rng)
            if days[0] > today and rng.random() < 0.3:
                status = LeaveStatus.APPROVED
            add_request(e.id, days, status, _pick_type(rng))

    # ----- attendance
    leave_days = {
        (r.employee_id, d)
        for r in requests if r.status == LeaveStatus.APPROVED
        for d in _working_dates(r.start_date, r.end_date, holiday_dates)
    }
    attendance: list[AttendanceRecord] = []
    for day in _working_dates(window_start, attendance_end, holiday_dates):
        for e in active:
            if (e.id, day) in leave_days:
                status, check_in = AttendanceStatus.LEAVE, None
            else:
                status = rng.choices([AttendanceStatus.PRESENT, AttendanceStatus.REMOTE,
                                      AttendanceStatus.ABSENT], weights=[82, 13, 5])[0]
                check_in = None
                if status != AttendanceStatus.ABSENT:
                    offset = rng.randint(1, 40) if rng.random() < 0.15 else -rng.randint(0, 30)
                    minutes = 9 * 60 + offset
                    check_in = f"{minutes // 60:02d}:{minutes % 60:02d}"
            attendance.append(AttendanceRecord(
                employee_id=e.id, date=day, status=status, check_in=check_in,
                scheduled_start=SCHEDULED_START, is_demo=True,
            ))

    # ----- balances (used = approved working days this year; pending is computed later)
    used: dict[tuple[str, LeaveType], int] = {}
    for r in requests:
        if r.status == LeaveStatus.APPROVED and r.start_date.year == today.year:
            used[(r.employee_id, r.leave_type)] = used.get((r.employee_id, r.leave_type), 0) + (
                r.working_days)
    balances = [
        LeaveBalanceRecord(employee_id=e.id, leave_type=lt, year=today.year,
                           entitled=Decimal(entitled), used=Decimal(used.get((e.id, lt), 0)),
                           as_of=today, is_demo=True)
        for e in active for lt, entitled in ENTITLEMENTS.items()
    ]

    # ----- payroll totals (department aggregates only; no per-employee pay anywhere)
    payroll: list[PayrollTotalRecord] = []
    cents = Decimal("0.01")
    for months_back in (2, 1, 0):
        period = _add_months(month_start, -months_back)
        for dept in DEPARTMENTS:
            heads = sum(1 for e in active if e.department == dept)
            gross = Decimal(MONTHLY_GROSS[dept] * heads) * Decimal(
                str(round(rng.uniform(0.97, 1.03), 4)))
            gross = gross.quantize(cents)
            payroll.append(PayrollTotalRecord(
                period=f"{period:%Y-%m}", department=dept, headcount_paid=heads,
                gross_total=gross, net_total=(gross * Decimal("0.8")).quantize(cents),
                currency=CURRENCY, is_demo=True,
            ))

    return DemoData(
        departments=[DepartmentRecord(name=d, is_demo=True) for d in DEPARTMENTS],
        leave_types=[LeaveTypeRecord(id=t, label=LEAVE_LABELS[t], is_demo=True)
                     for t in LeaveType],
        holidays=holidays, employees=employees,
        leave_requests=sorted(requests, key=lambda r: (r.created_at, r.id)),
        attendance=attendance, balances=balances, payroll=payroll,
        attendance_end=attendance_end,
    )


# --------------------------------------------------------------------------- writing


def generate_password() -> str:
    return secrets.token_urlsafe(12)


async def run_seed(
    engine: AsyncEngine,
    *,
    today: date,
    force: bool = False,
    reset: bool = False,
    rng_seed: int = DEFAULT_SEED,
    password_factory: Callable[[], str] = generate_password,
    hasher: Callable[[str], str] = hash_password,
    now: datetime | None = None,
) -> SeedReport:
    """Write the demo data. Raises ``SeedRefused`` (exit 2) when seeding would be unsafe."""
    try:
        await assert_at_head(engine)
    except ConfigurationError:
        raise SeedRefused(OUT_OF_DATE_MESSAGE) from None

    data = build_demo_data(today, rng_seed=rng_seed)
    created_at = now or datetime.now(UTC)
    async with session_factory(engine)() as session, session.begin():
        admin = AdminRepo(session)
        non_demo = await admin.non_demo_counts()
        if non_demo and not force:
            tables = ", ".join(sorted(non_demo))
            raise SeedRefused(f"Non-demo rows exist ({tables}); use --force to seed anyway")
        if any((await admin.demo_counts()).values()):
            if not reset:
                raise SeedRefused("Demo data is already present; use --reset to recreate it")
            await admin.delete_demo_rows()

        credentials: list[DemoCredential] = []
        users: list[UserRecord] = []
        for uid, username, role, eid in _DEMO_USERS:
            password = password_factory()
            credentials.append(DemoCredential(username, role, eid, password))
            users.append(UserRecord(id=uid, username=username, password_hash=hasher(password),
                                    role=role, employee_id=eid, is_demo=True,
                                    created_at=created_at))

        employees, leave = EmployeeRepo(session), LeaveRepo(session)
        await employees.insert_departments(data.departments)
        await leave.insert_leave_types(data.leave_types)
        await HolidayRepo(session).insert_many(data.holidays)
        await employees.insert_many(data.employees)
        user_repo = UserRepo(session)
        for user in users:
            await user_repo.insert(user)
        await leave.insert_balances(data.balances)
        await leave.insert_many(data.leave_requests)
        await AttendanceRepo(session).insert_many(data.attendance)
        await PayrollRepo(session).insert_many(data.payroll)
        counts = await admin.demo_counts()

    return SeedReport(counts=counts, credentials=credentials, attendance_end=data.attendance_end)
