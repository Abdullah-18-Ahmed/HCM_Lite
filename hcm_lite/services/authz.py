"""Authorization and scoping (research D-06, FR-004–006).

Every service method calls :meth:`Authz.require` and/or :meth:`Authz.resolve_scope` before any
repository call. A denial raises ``AccessDenied`` and writes an ``access_denied`` audit row.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from hcm_lite.db.repositories import EmployeeRepo
from hcm_lite.errors import AccessDenied
from hcm_lite.models.domain import (
    AccessScope,
    AuditAction,
    AuditOutcome,
    AuthenticatedUser,
    Role,
    Scope,
)
from hcm_lite.services.audit import Auditor


class Capability(StrEnum):
    OWN_DATA = "own_data"  # own profile, attendance, leave requests, balance
    LEAVE_SELF = "leave_self"  # leave draft + confirm (self)
    METRICS = "metrics"  # headcount / attendance / late comers / leave summary
    EMPLOYEE_SEARCH = "employee_search"
    PENDING_LEAVE = "pending_leave"
    PAYROLL = "payroll"


_SELF = frozenset({Capability.OWN_DATA, Capability.LEAVE_SELF})
_TEAM = _SELF | {Capability.METRICS, Capability.EMPLOYEE_SEARCH, Capability.PENDING_LEAVE}

PERMISSIONS: dict[Role, frozenset[Capability]] = {
    Role.EMPLOYEE: _SELF,
    Role.MANAGER: _TEAM,
    Role.HR_ADMIN: _TEAM | {Capability.PAYROLL},
}

_DOC_SCOPES: dict[Role, frozenset[str]] = {
    Role.EMPLOYEE: frozenset({AccessScope.ALL_EMPLOYEES.value}),
    Role.MANAGER: frozenset({AccessScope.ALL_EMPLOYEES.value, AccessScope.MANAGERS.value}),
    Role.HR_ADMIN: frozenset({AccessScope.ALL_EMPLOYEES.value, AccessScope.MANAGERS.value,
                              AccessScope.HR_ADMIN.value}),
}


def allowed_doc_scopes(role: Role | str) -> frozenset[str]:
    """Document access scopes a role may read. ``restricted`` is never included."""
    return _DOC_SCOPES[Role(role)]


def has(user: AuthenticatedUser, capability: Capability) -> bool:
    return capability in PERMISSIONS[user.role]


class Authz:
    def __init__(self, session_factory: Any, auditor: Auditor) -> None:
        self._sf = session_factory
        self._auditor = auditor

    async def require(self, user: AuthenticatedUser, capability: Capability) -> None:
        if not has(user, capability):
            await self._auditor.audit(AuditAction.ACCESS_DENIED, AuditOutcome.DENIED,
                                      actor=user.user_id, target=str(capability))
            raise AccessDenied(str(capability))

    async def resolve_scope(self, user: AuthenticatedUser) -> Scope:
        """employee → self; manager → self + direct reports (queried now); hr_admin → all."""
        if user.role == Role.HR_ADMIN:
            return Scope(kind="all", employee_ids=None)
        if user.role == Role.MANAGER:
            async with self._sf() as session:
                team = await EmployeeRepo(session).team_of(user.employee_id)
            ids = frozenset({user.employee_id, *(e.id for e in team)})
            return Scope(kind="team", employee_ids=ids)
        return Scope(kind="self", employee_ids=frozenset({user.employee_id}))
