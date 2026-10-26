"""T016: authorization matrix (research D-06) on the seeded temp DB."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from hcm_lite.errors import AccessDenied
from hcm_lite.models.domain import Role
from hcm_lite.services.authz import (
    PERMISSIONS,
    Capability,
    allowed_doc_scopes,
    can_manage_role,
    has,
)

# (employee, manager, hr_admin, admin)
MATRIX = {
    Capability.OWN_DATA: (True, True, True, True),
    Capability.LEAVE_SELF: (True, True, True, True),
    Capability.METRICS: (False, True, True, True),
    Capability.EMPLOYEE_SEARCH: (False, True, True, True),
    Capability.PENDING_LEAVE: (False, True, True, True),
    Capability.PAYROLL: (False, False, True, True),
    Capability.MANAGE_EMPLOYEES: (False, False, True, True),
    Capability.MANAGE_HR: (False, False, False, True),
}
ROLES = (Role.EMPLOYEE, Role.MANAGER, Role.HR_ADMIN, Role.ADMIN)


def _db(tmp_path):
    return closing(sqlite3.connect(tmp_path / "hcm_test.db"))


@pytest.mark.parametrize("capability", list(MATRIX))
def test_full_matrix(capability, make_user):
    for role, allowed in zip(ROLES, MATRIX[capability], strict=True):
        assert has(make_user(role), capability) is allowed, (role, capability)
    assert set(PERMISSIONS) == set(ROLES)


async def test_resolve_scope_self(authz, make_user):
    scope = await authz.resolve_scope(make_user(Role.EMPLOYEE))
    assert scope.kind == "self" and scope.employee_ids == frozenset({"E1001"})


async def test_resolve_scope_team_is_direct_reports_plus_self(authz, make_user, tmp_path):
    scope = await authz.resolve_scope(make_user(Role.MANAGER))
    with _db(tmp_path) as db:
        reports = {r[0] for r in db.execute("SELECT id FROM employees WHERE manager_id='M1002'")}
    assert scope.kind == "team"
    assert scope.employee_ids == frozenset(reports | {"M1002"})
    assert "E1001" in scope.employee_ids and len(reports) >= 2


async def test_resolve_scope_all(authz, make_user):
    scope = await authz.resolve_scope(make_user(Role.HR_ADMIN))
    assert scope.kind == "all" and scope.employee_ids is None


async def test_resolve_scope_admin_is_all(authz, make_user):
    scope = await authz.resolve_scope(make_user(Role.ADMIN))
    assert scope.kind == "all" and scope.employee_ids is None


def test_can_manage_role():
    assert can_manage_role(Role.ADMIN, Role.HR_ADMIN)
    assert can_manage_role(Role.ADMIN, Role.EMPLOYEE)
    assert can_manage_role(Role.HR_ADMIN, Role.EMPLOYEE)
    # nobody may manage an admin; hr_admin may not manage hr_admin; employee may manage nobody
    assert not can_manage_role(Role.ADMIN, Role.ADMIN)
    assert not can_manage_role(Role.HR_ADMIN, Role.HR_ADMIN)
    assert not can_manage_role(Role.HR_ADMIN, Role.ADMIN)
    assert not can_manage_role(Role.EMPLOYEE, Role.EMPLOYEE)


def test_allowed_doc_scopes():
    assert allowed_doc_scopes(Role.EMPLOYEE) == {"all_employees"}
    assert allowed_doc_scopes(Role.MANAGER) == {"all_employees", "managers"}
    assert allowed_doc_scopes(Role.HR_ADMIN) == {"all_employees", "managers", "hr_admin"}
    for role in ROLES:
        assert "restricted" not in allowed_doc_scopes(role)


async def test_require_allows(authz, make_user, tmp_path):
    await authz.require(make_user(Role.HR_ADMIN), Capability.PAYROLL)
    with _db(tmp_path) as db:
        assert db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0


async def test_require_denies_and_audits(authz, make_user, tmp_path):
    with pytest.raises(AccessDenied) as exc:
        await authz.require(make_user(Role.EMPLOYEE), Capability.PAYROLL)
    assert exc.value.capability == "payroll"
    with _db(tmp_path) as db:
        rows = db.execute("SELECT action, outcome, actor_user_id, target, channel,"
                          " correlation_id FROM audit_events").fetchall()
    assert len(rows) == 1
    action, outcome, actor, target, channel, cid = rows[0]
    assert (action, outcome, actor, target, channel) == (
        "access_denied", "denied", "U0001", "payroll", "chat")
    assert cid
