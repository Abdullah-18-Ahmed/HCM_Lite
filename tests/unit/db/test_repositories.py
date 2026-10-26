"""T014: repositories against a migrated temp SQLite DB (constraints enforced by the DB)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from hcm_lite.db.repositories import (
    AttendanceRepo,
    AuditRepo,
    EmployeeRepo,
    HolidayRepo,
    LeaveRepo,
    LoginFailureRepo,
    PayrollRepo,
    UserRepo,
)
from hcm_lite.errors import DatabaseError, ValidationError
from hcm_lite.models.domain import (
    AttendanceRecord,
    AttendanceStatus,
    AuditAction,
    AuditEventRecord,
    AuditOutcome,
    Channel,
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

NOW = datetime(2026, 10, 25, 9, 30, tzinfo=UTC)


def _emp(eid: str, dept: str = "Engineering", manager: str | None = None,
         status: EmploymentStatus = EmploymentStatus.ACTIVE, name: str | None = None):
    return EmployeeRecord(
        id=eid, full_name=name or f"Demo Person {eid}", department=dept, job_title="Engineer",
        employment_status=status, hire_date=date(2024, 1, 15), manager_id=manager,
    )


def _user(uid: str, username: str, eid: str, role: Role = Role.EMPLOYEE) -> UserRecord:
    return UserRecord(id=uid, username=username, email=f"{uid.lower()}@demo.hcm",
                      password_hash="pbkdf2_sha256$1$a$b", role=role, employee_id=eid,
                      created_at=NOW)


def _leave(ref: str, eid: str = "E1001", start=date(2026, 10, 26), end=date(2026, 10, 27),
           key: str | None = None, status=LeaveStatus.PENDING, lt=LeaveType.ANNUAL,
           created_at=NOW, days: int = 2) -> LeaveRequestRecord:
    return LeaveRequestRecord(
        id=ref, employee_id=eid, leave_type=lt, start_date=start, end_date=end,
        working_days=days, reason="Family event", status=status,
        source=LeaveSource.ASSISTANT, idempotency_key=key, created_by="U0001",
        created_at=created_at,
    )


@pytest.fixture
async def base(session):
    """Two departments, a manager with two reports, one other employee, one user."""
    emp = EmployeeRepo(session)
    await emp.insert_departments([DepartmentRecord(name="Engineering"),
                                  DepartmentRecord(name="Sales")])
    await emp.insert(_emp("M1002"))
    await emp.insert_many([
        _emp("E1001", manager="M1002", name="Ayla Demo"),
        _emp("E1004", manager="M1002", status=EmploymentStatus.INACTIVE),
        _emp("E1005", dept="Sales"),
    ])
    await LeaveRepo(session).insert_leave_types(
        [LeaveTypeRecord(id=t, label=t.value.title()) for t in LeaveType]
    )
    await UserRepo(session).insert(_user("U0001", "employee", "E1001"))
    return session


# --------------------------------------------------------------------------- users


async def test_user_roundtrip_and_duplicate_username(base):
    repo = UserRepo(base)
    got = await repo.get_by_username("employee")
    assert got is not None and got.id == "U0001" and got.role is Role.EMPLOYEE
    assert got.created_at == NOW and got.created_at.tzinfo is not None
    assert (await repo.get("U0001")) == got
    assert await repo.get("U9999") is None
    with pytest.raises(ValidationError) as exc:
        await repo.insert(_user("U0002", "employee", "M1002"))
    assert exc.value.field == "username"
    # the session stays usable after the mapped error
    assert (await repo.get_by_username("employee")).id == "U0001"


async def test_user_duplicate_employee_link_rejected(base):
    with pytest.raises(ValidationError) as exc:
        await UserRepo(base).insert(_user("U0002", "other", "E1001"))
    assert exc.value.field == "employee_id"


async def test_user_unknown_employee_rejected_by_fk(base):
    with pytest.raises(ValidationError):
        await UserRepo(base).insert(_user("U0002", "ghost", "E9999"))


async def test_user_lock_and_next_id(base):
    repo = UserRepo(base)
    until = NOW + timedelta(minutes=15)
    await repo.set_locked_until("U0001", until)
    assert (await repo.get("U0001")).locked_until == until
    await repo.set_locked_until("U0001", None)
    assert (await repo.get("U0001")).locked_until is None
    assert await repo.next_id() == "U0002"


async def test_login_failures_count_and_clear(base):
    repo = LoginFailureRepo(base)
    for minutes in (20, 10, 5, 1):
        await repo.add("U0001", NOW - timedelta(minutes=minutes))
    assert await repo.count_since("U0001", NOW - timedelta(minutes=15)) == 3
    await repo.clear("U0001")
    assert await repo.count_since("U0001", NOW - timedelta(days=1)) == 0


# --------------------------------------------------------------------------- employees


async def test_team_of_returns_direct_reports(base):
    repo = EmployeeRepo(base)
    team = await repo.team_of("M1002")
    assert {e.id for e in team} == {"E1001", "E1004"}
    assert all(e.manager_id == "M1002" for e in team)
    assert {e.id for e in await repo.team_of("M1002", active_only=True)} == {"E1001"}
    assert await repo.team_of("E1005") == []


async def test_employee_list_respects_explicit_ids(base):
    repo = EmployeeRepo(base)
    assert {e.id for e in await repo.list(employee_ids={"E1001", "E1005"})} == {"E1001", "E1005"}
    assert len(await repo.list(employee_ids=None)) == 4
    assert await repo.list(employee_ids=set()) == []
    assert (await repo.get("E1001")).full_name == "Ayla Demo"
    found = await repo.search(employee_ids=None, name="ayla")
    assert [e.id for e in found] == ["E1001"]


async def test_headcount_group_by_matches_python(base):
    repo = EmployeeRepo(base)
    rows = await repo.list(employee_ids=None)
    expected = Counter(e.department for e in rows if e.employment_status == "active")
    assert await repo.headcount_by_department(employee_ids=None) == dict(expected)
    assert await repo.headcount_by_department(employee_ids={"E1001", "E1004"}) == {
        "Engineering": 1
    }


async def test_employee_unknown_department_rejected(base):
    with pytest.raises(ValidationError):
        await EmployeeRepo(base).insert(_emp("E1010", dept="Nowhere"))


# --------------------------------------------------------------------------- attendance


def _att(eid, day, status=AttendanceStatus.PRESENT, check_in="09:00"):
    return AttendanceRecord(employee_id=eid, date=day, status=status,
                            check_in=None if status in ("absent", "leave") else check_in,
                            scheduled_start="09:00")


async def test_attendance_unknown_employee_rejected_by_fk(base):
    with pytest.raises(ValidationError):
        await AttendanceRepo(base).insert(_att("E9999", date(2026, 10, 1)))


async def test_attendance_status_late_rejected_by_check(base):
    bad = AttendanceRecord.model_construct(
        employee_id="E1001", date=date(2026, 10, 1), status="late", check_in="09:30",
        scheduled_start="09:00", is_demo=False, id=None,
    )
    with pytest.raises(ValidationError) as exc:
        await AttendanceRepo(base).insert(bad)
    assert "status" in exc.value.field
    # and directly at the database, bypassing the repository
    with pytest.raises(Exception, match="CHECK constraint failed"):
        await base.execute(text(
            "INSERT INTO attendance (employee_id, date, status, check_in, scheduled_start,"
            " is_demo) VALUES ('E1001', '2026-10-02', 'late', '09:30', '09:00', 0)"
        ))
    await base.rollback()


async def test_attendance_present_requires_check_in(base):
    bad = AttendanceRecord(employee_id="E1001", date=date(2026, 10, 1), status="present",
                           check_in=None, scheduled_start="09:00")
    with pytest.raises(ValidationError):
        await AttendanceRepo(base).insert(bad)


async def test_attendance_duplicate_day_rejected(base):
    repo = AttendanceRepo(base)
    await repo.insert(_att("E1001", date(2026, 10, 1)))
    with pytest.raises(ValidationError):
        await repo.insert(_att("E1001", date(2026, 10, 1), AttendanceStatus.REMOTE))


async def test_attendance_by_ids_and_range_with_group_by(base):
    repo = AttendanceRepo(base)
    statuses = [AttendanceStatus.PRESENT, AttendanceStatus.REMOTE, AttendanceStatus.ABSENT,
                AttendanceStatus.LEAVE, AttendanceStatus.PRESENT]
    rows = []
    for i, st in enumerate(statuses):
        for eid in ("E1001", "E1005", "M1002"):
            rows.append(_att(eid, date(2026, 10, 5 + i), st))
    await repo.insert_many(rows)
    got = await repo.list(employee_ids={"E1001", "M1002"}, start=date(2026, 10, 6),
                          end=date(2026, 10, 8))
    assert {(r.employee_id, r.date) for r in got} == {
        (e, date(2026, 10, d)) for e in ("E1001", "M1002") for d in (6, 7, 8)
    }
    assert all(r.id is not None for r in got)
    counts = await repo.count_by_status(employee_ids={"E1001", "M1002"},
                                        start=date(2026, 10, 1), end=date(2026, 10, 31))
    expected = Counter(r.status.value for r in rows if r.employee_id in {"E1001", "M1002"})
    assert counts == dict(expected)
    everyone = await repo.count_by_status(employee_ids=None, start=date(2026, 10, 1),
                                          end=date(2026, 10, 31))
    assert sum(everyone.values()) == len(rows)


# --------------------------------------------------------------------------- leave


async def test_leave_end_before_start_rejected_by_check(base):
    bad = _leave("LR-20261025-AAAA", start=date(2026, 10, 27), end=date(2026, 10, 26))
    with pytest.raises(ValidationError) as exc:
        await LeaveRepo(base).insert(bad)
    assert "end" in exc.value.field


async def test_leave_insert_idempotent(base):
    repo = LeaveRepo(base)
    first, created = await repo.insert_idempotent(_leave("LR-20261025-AAAA", key="k-1"))
    assert created is True and first.id == "LR-20261025-AAAA"
    again, created2 = await repo.insert_idempotent(_leave("LR-20261025-BBBB", key="k-1"))
    assert created2 is False
    assert again == first
    assert await repo.get("LR-20261025-BBBB") is None
    assert len(await repo.list_for_employees(employee_ids={"E1001"})) == 1


async def test_leave_insert_idempotent_maps_other_integrity_errors(base):
    repo = LeaveRepo(base)
    with pytest.raises(ValidationError):
        await repo.insert_idempotent(_leave("LR-20261025-CCCC", eid="E9999", key="k-2"))
    await repo.insert_idempotent(_leave("LR-20261025-DDDD", key="k-3"))
    with pytest.raises(ValidationError):  # same reference, different key
        await repo.insert_idempotent(_leave("LR-20261025-DDDD", key="k-4"))


async def test_leave_list_newest_first_and_counts(base):
    repo = LeaveRepo(base)
    recs = [
        _leave("LR-1", created_at=NOW - timedelta(days=3), status=LeaveStatus.APPROVED,
               start=date(2026, 10, 5), end=date(2026, 10, 6)),
        _leave("LR-2", created_at=NOW - timedelta(days=1)),
        _leave("LR-3", eid="E1005", created_at=NOW, status=LeaveStatus.REJECTED,
               lt=LeaveType.SICK, start=date(2026, 10, 12), end=date(2026, 10, 12), days=1),
    ]
    await repo.insert_many(recs)
    mine = await repo.list_for_employees(employee_ids={"E1001"})
    assert [r.id for r in mine] == ["LR-2", "LR-1"]
    assert [r.id for r in await repo.list_for_employees(employee_ids=None, limit=1)] == ["LR-3"]
    overlap = await repo.list_for_employees(employee_ids=None, start=date(2026, 10, 6),
                                            end=date(2026, 10, 12))
    assert {r.id for r in overlap} == {"LR-1", "LR-3"}
    by_status = await repo.count_by_status(employee_ids=None, start=date(2026, 10, 1),
                                           end=date(2026, 10, 31))
    assert by_status == dict(Counter(r.status.value for r in recs))
    days = await repo.sum_days_by_type(employee_ids={"E1001"}, start=date(2026, 1, 1),
                                       end=date(2026, 12, 31), statuses={"approved"})
    assert days == {"annual": 2}


async def test_leave_balances(base):
    repo = LeaveRepo(base)
    await repo.insert_balances([
        LeaveBalanceRecord(employee_id="E1001", leave_type=LeaveType.ANNUAL, year=2026,
                           entitled=Decimal("20"), used=Decimal("3.5"), as_of=date(2026, 10, 25)),
    ])
    got = await repo.balances_for("E1001", 2026)
    assert len(got) == 1 and got[0].used == Decimal("3.50")
    with pytest.raises(ValidationError):  # UNIQUE (employee_id, leave_type, year)
        await repo.insert_balances([got[0].model_copy(update={"id": None})])
    bad = LeaveBalanceRecord.model_construct(
        id=None, employee_id="E1005", leave_type=LeaveType.ANNUAL, year=2026,
        entitled=Decimal("-1"), used=Decimal("0"), as_of=date(2026, 10, 25), is_demo=False)
    with pytest.raises(ValidationError):
        await repo.insert_balances([bad])


# --------------------------------------------------------------------------- payroll, holidays, audit


async def test_payroll_by_period(base):
    repo = PayrollRepo(base)
    await repo.insert_many([
        PayrollTotalRecord(period="2026-09", department="Engineering", headcount_paid=3,
                           gross_total=Decimal("15000.10"), net_total=Decimal("12000.05"),
                           currency="USD"),
        PayrollTotalRecord(period="2026-09", department="Sales", headcount_paid=1,
                           gross_total=Decimal("4000.20"), net_total=Decimal("3200.10"),
                           currency="USD"),
        PayrollTotalRecord(period="2026-08", department="Sales", headcount_paid=1,
                           gross_total=Decimal("3900"), net_total=Decimal("3100"),
                           currency="USD"),
    ])
    sept = await repo.by_period("2026-09")
    assert {p.department for p in sept} == {"Engineering", "Sales"}
    assert [p.department for p in await repo.by_period("2026-09", department="Sales")] == [
        "Sales"
    ]
    totals = await repo.totals_for_period("2026-09")
    assert totals == (4, Decimal("19000.30"), Decimal("15200.15"))
    assert await repo.by_period("2026-07") == []
    with pytest.raises(ValidationError):  # UNIQUE (period, department)
        await repo.insert_many([sept[0].model_copy(update={"id": None})])


async def test_holidays_between(base):
    repo = HolidayRepo(base)
    await repo.insert_many([HolidayRecord(date=date(2026, 8, 14), name="Demo Holiday"),
                            HolidayRecord(date=date(2026, 12, 25), name="Demo Winter")])
    assert [h.date for h in await repo.between(date(2026, 8, 1), date(2026, 10, 31))] == [
        date(2026, 8, 14)
    ]


async def test_audit_insert_and_check(base):
    repo = AuditRepo(base)
    rec = await repo.insert(AuditEventRecord(
        at=NOW, actor_user_id="U0001", action=AuditAction.LOGIN_SUCCESS, channel=Channel.CHAT,
        outcome=AuditOutcome.OK, correlation_id="c0ffee00-0000-0000-0000-000000000000"))
    assert rec.id is not None
    recent = await repo.list_recent(limit=5)
    assert recent == [rec]
    bad = AuditEventRecord.model_construct(
        id=None, at=NOW, actor_user_id=None, action="message_sent", channel="chat",
        target=None, outcome="ok", correlation_id="x")
    with pytest.raises(ValidationError):
        await repo.insert(bad)


async def test_operational_error_maps_to_database_error(tmp_path):
    from hcm_lite.db.engine import create_engine_for_url, session_factory

    bad = tmp_path / "not_a_db.db"
    bad.write_bytes(b"this is not a sqlite database" * 100)
    eng = create_engine_for_url(f"sqlite+aiosqlite:///{bad.as_posix()}")
    try:
        async with session_factory(eng)() as s:
            with pytest.raises(DatabaseError):
                await UserRepo(s).get_by_username("employee")
    finally:
        await eng.dispose()


async def test_missing_table_maps_to_database_error(engine):
    from hcm_lite.db.engine import session_factory

    async with session_factory(engine)() as s:  # unmigrated DB: no tables
        with pytest.raises(DatabaseError):
            await EmployeeRepo(s).team_of("M1002")
