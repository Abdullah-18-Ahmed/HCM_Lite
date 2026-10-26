"""User administration (real-data user management).

Create, edit, deactivate and delete user accounts and their employee profiles. Every method takes
the acting :class:`AuthenticatedUser`, checks authorization first (constitution Art. VIII, XVI),
writes an audit row, and goes through the repositories only — no SQL or ORM here (Art. IX.1.4).

Role hierarchy: ``admin`` > ``hr_admin`` > ``employee`` (``manager`` is kept for back-compat but
is not created here). ``admin`` may manage ``hr_admin`` and ``employee``; ``hr_admin`` may manage
``employee`` only; nobody may manage an ``admin`` and nobody may manage their own account here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from hcm_lite.db.repositories import EmployeeRepo, LeaveRepo, UserRepo
from hcm_lite.errors import AccessDenied, NotFound, ValidationError
from hcm_lite.models.domain import (
    AuditAction,
    AuditOutcome,
    AuthenticatedUser,
    Channel,
    EmployeeRecord,
    EmploymentStatus,
    LeaveBalanceRecord,
    LeaveTypeRecord,
    Role,
    UserRecord,
)

# Standard leave catalogue + default yearly entitlement (days) given to every new user, so
# their leave balance and smart-leave features work immediately.
_DEFAULT_LEAVE_TYPES = [("annual", "Annual"), ("sick", "Sick"), ("casual", "Casual"),
                        ("unpaid", "Unpaid"), ("other", "Other")]
_DEFAULT_ENTITLEMENTS = {"annual": 20, "sick": 10, "casual": 6}
from hcm_lite.services.audit import Auditor
from hcm_lite.services.authz import Authz, Capability, can_manage_role
from hcm_lite.services.passwords import hash_password

MIN_PASSWORD_LENGTH = 8
ADMIN_DEPARTMENT = "Administration"
ADMIN_JOB_TITLE = "Administrator"

Clock = Callable[[], datetime]


class UserAdminService:
    def __init__(self, session_factory: Any, authz: Authz, auditor: Auditor, *,
                 hasher: Callable[[str], str] = hash_password, clock: Clock | None = None) -> None:
        self._sf = session_factory
        self._authz = authz
        self._auditor = auditor
        self._hash = hasher
        self._clock = clock or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------ helpers

    def _now(self) -> datetime:
        return self._clock()

    def _today(self) -> date:
        return self._clock().date()

    @staticmethod
    def _require_password(password: Any, field: str = "password") -> None:
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(field, f"must be at least {MIN_PASSWORD_LENGTH} characters")

    @staticmethod
    def _clean_email(email: Any) -> str:
        if not isinstance(email, str) or not email.strip():
            raise ValidationError("email", "is required")
        return email.strip()

    @staticmethod
    def _as_role(value: Any) -> Role:
        try:
            return Role(value)
        except ValueError:
            raise ValidationError("role", "is not a valid role") from None

    def _block_self(self, actor: AuthenticatedUser, user_id: str) -> None:
        if actor.user_id == user_id:
            raise AccessDenied("manage_self")

    @staticmethod
    def _profile(row: dict[str, Any]) -> dict[str, Any]:
        created = row["created_at"]
        return {
            "user_id": row["user_id"], "email": row["email"], "name": row["name"],
            "role": str(row["role"]), "department": row["department"],
            "job_title": row["job_title"], "active": bool(row["active"]),
            "created_at": created.isoformat() if created is not None else None,
        }

    # ------------------------------------------------------------------ reads

    async def admin_exists(self) -> bool:
        async with self._sf() as session:
            return await UserRepo(session).exists_with_role(Role.ADMIN.value)

    async def list_users(self, actor: AuthenticatedUser) -> list[dict[str, Any]]:
        await self._authz.require(actor, Capability.MANAGE_EMPLOYEES)
        roles = None if actor.role == Role.ADMIN else [Role.EMPLOYEE.value]
        async with self._sf() as session:
            rows = await UserRepo(session).list_profiles(roles=roles)
        return [self._profile(r) for r in rows]

    # ------------------------------------------------------------------ writes

    async def create_user(self, actor: AuthenticatedUser, *, email: str, password: str,
                          name: str, role: str, department: str, job_title: str
                          ) -> dict[str, Any]:
        await self._authz.require(actor, Capability.MANAGE_EMPLOYEES)
        role_value = self._as_role(role)
        if not can_manage_role(actor.role, role_value):
            raise AccessDenied("manage_role")
        email = self._clean_email(email)
        self._require_password(password)
        async with self._sf() as session, session.begin():
            users, employees = UserRepo(session), EmployeeRepo(session)
            if await users.get_by_email(email) is not None:
                raise ValidationError("email", "already in use")
            await employees.ensure_department(department)
            employee_id = await employees.next_id()
            user_id = await users.next_id()
            await employees.insert(EmployeeRecord(
                id=employee_id, full_name=name, department=department, job_title=job_title,
                employment_status=EmploymentStatus.ACTIVE, hire_date=self._today(),
                manager_id=None, is_demo=False))
            await users.insert(UserRecord(
                id=user_id, username=email, email=email, password_hash=self._hash(password),
                role=role_value, employee_id=employee_id, active=True, is_demo=False,
                created_at=self._now()))
            await self._ensure_default_balances(session, employee_id)
        await self._audit(AuditAction.USER_CREATED, actor, user_id)
        return {"user_id": user_id}

    async def _ensure_default_balances(self, session: Any, employee_id: str) -> None:
        """Give a new employee the standard leave types (if missing) and default balances."""
        leave = LeaveRepo(session)
        have = {t.id for t in await leave.list_leave_types()}
        missing = [LeaveTypeRecord(id=tid, label=label, is_demo=False)
                   for tid, label in _DEFAULT_LEAVE_TYPES if tid not in have]
        if missing:
            await leave.insert_leave_types(missing)
        year = self._today().year
        await leave.insert_balances([
            LeaveBalanceRecord(employee_id=employee_id, leave_type=lt, year=year,
                               entitled=Decimal(ent), used=Decimal(0), as_of=self._today(),
                               is_demo=False)
            for lt, ent in _DEFAULT_ENTITLEMENTS.items()])

    async def update_user(self, actor: AuthenticatedUser, user_id: str, *, name: str | None = None,
                          department: str | None = None, job_title: str | None = None,
                          role: str | None = None) -> dict[str, Any]:
        await self._authz.require(actor, Capability.MANAGE_EMPLOYEES)
        self._block_self(actor, user_id)
        new_role = self._as_role(role) if role is not None else None
        async with self._sf() as session, session.begin():
            users, employees = UserRepo(session), EmployeeRepo(session)
            target = await users.get(user_id)
            if target is None:
                raise NotFound("user")
            if not can_manage_role(actor.role, target.role):
                raise AccessDenied("manage_role")
            if new_role is not None:
                if not can_manage_role(actor.role, new_role):
                    raise AccessDenied("manage_role")
                await users.set_role(user_id, new_role.value)
            if department is not None:
                await employees.ensure_department(department)
            await employees.update_profile(target.employee_id, full_name=name,
                                           department=department, job_title=job_title)
        await self._audit(AuditAction.USER_UPDATED, actor, user_id)
        return {"ok": True}

    async def set_active(self, actor: AuthenticatedUser, user_id: str, active: bool
                         ) -> dict[str, Any]:
        await self._authz.require(actor, Capability.MANAGE_EMPLOYEES)
        self._block_self(actor, user_id)
        async with self._sf() as session, session.begin():
            users = UserRepo(session)
            target = await users.get(user_id)
            if target is None:
                raise NotFound("user")
            if not can_manage_role(actor.role, target.role):
                raise AccessDenied("manage_role")
            await users.set_active(user_id, bool(active))
        action = AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED
        await self._audit(action, actor, user_id)
        return {"ok": True}

    async def delete_user(self, actor: AuthenticatedUser, user_id: str) -> None:
        await self._authz.require(actor, Capability.MANAGE_EMPLOYEES)
        self._block_self(actor, user_id)
        async with self._sf() as session, session.begin():
            users = UserRepo(session)
            target = await users.get(user_id)
            if target is None:
                raise NotFound("user")
            if not can_manage_role(actor.role, target.role):
                raise AccessDenied("manage_role")
            await users.delete_with_profile(user_id, target.employee_id)
        await self._audit(AuditAction.USER_DELETED, actor, user_id)

    async def bootstrap_admin(self, *, email: str, password: str, name: str) -> dict[str, Any]:
        """Create the first admin account. Fails once any admin exists (no auth required)."""
        if await self.admin_exists():
            raise ValidationError("admin", "An admin already exists")
        email = self._clean_email(email)
        self._require_password(password)
        async with self._sf() as session, session.begin():
            users, employees = UserRepo(session), EmployeeRepo(session)
            if await users.get_by_email(email) is not None:
                raise ValidationError("email", "already in use")
            await employees.ensure_department(ADMIN_DEPARTMENT)
            employee_id = await employees.next_id()
            user_id = await users.next_id()
            await employees.insert(EmployeeRecord(
                id=employee_id, full_name=name, department=ADMIN_DEPARTMENT,
                job_title=ADMIN_JOB_TITLE, employment_status=EmploymentStatus.ACTIVE,
                hire_date=self._today(), manager_id=None, is_demo=False))
            await users.insert(UserRecord(
                id=user_id, username=email, email=email, password_hash=self._hash(password),
                role=Role.ADMIN, employee_id=employee_id, active=True, is_demo=False,
                created_at=self._now()))
            await self._ensure_default_balances(session, employee_id)
        await self._auditor.audit(AuditAction.ADMIN_CREATED, AuditOutcome.OK, actor=user_id,
                                  target=user_id, channel=Channel.API)
        return {"user_id": user_id}

    async def _audit(self, action: AuditAction, actor: AuthenticatedUser, target: str) -> None:
        await self._auditor.audit(action, AuditOutcome.OK, actor=actor.user_id, target=target,
                                  channel=Channel.API)
