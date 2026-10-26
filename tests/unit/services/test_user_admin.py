"""UserAdminService on the seeded temp DB: authz, role hierarchy, CRUD and bootstrap."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from hcm_lite.errors import AccessDenied, NotFound, ValidationError
from hcm_lite.models.domain import Role
from hcm_lite.services.passwords import hash_password


@pytest.fixture
def user_admin(sf, authz, auditor):
    from hcm_lite.services.user_admin_service import UserAdminService

    return UserAdminService(sf, authz, auditor,
                            hasher=lambda p: hash_password(p, iterations=1_000))


def _rows(tmp_path, sql, params=()):
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db:
        return db.execute(sql, params).fetchall()


async def _admin_id(user_admin, admin_actor) -> str:
    users = await user_admin.list_users(admin_actor)
    return next(u["user_id"] for u in users if u["role"] == "admin")


# --------------------------------------------------------------------------- bootstrap


async def test_bootstrap_creates_admin_then_second_fails(user_admin):
    assert not await user_admin.admin_exists()
    result = await user_admin.bootstrap_admin(email="root@demo.hcm", password="rootpass1",
                                              name="Root Admin")
    assert result["user_id"].startswith("U")
    assert await user_admin.admin_exists()
    with pytest.raises(ValidationError) as exc:
        await user_admin.bootstrap_admin(email="root2@demo.hcm", password="rootpass1",
                                         name="Second")
    assert exc.value.field == "admin"


async def test_bootstrap_admin_has_profile(user_admin, make_user, tmp_path):
    await user_admin.bootstrap_admin(email="root@demo.hcm", password="rootpass1", name="Root")
    rows = _rows(tmp_path, "SELECT department, job_title FROM employees"
                           " WHERE department='Administration'")
    assert rows == [("Administration", "Administrator")]


# --------------------------------------------------------------------------- create / list


async def test_admin_creates_hr_and_employee(user_admin, make_user):
    admin = make_user(Role.ADMIN)
    await user_admin.bootstrap_admin(email="root@demo.hcm", password="rootpass1", name="Root")
    await user_admin.create_user(admin, email="hr1@x.hcm", password="pw123456", name="HR One",
                                 role="hr_admin", department="Engineering", job_title="HR")
    emp = await user_admin.create_user(admin, email="emp1@x.hcm", password="pw123456",
                                       name="Emp One", role="employee", department="Sales",
                                       job_title="Rep")
    assert emp["user_id"].startswith("U")
    users = await user_admin.list_users(admin)
    by_email = {u["email"]: u for u in users}
    assert by_email["hr1@x.hcm"]["role"] == "hr_admin"
    assert by_email["emp1@x.hcm"]["name"] == "Emp One"
    assert by_email["emp1@x.hcm"]["department"] == "Sales"


async def test_hr_lists_only_employees(user_admin, make_user):
    hr = make_user(Role.HR_ADMIN)
    users = await user_admin.list_users(hr)
    assert users and {u["role"] for u in users} == {"employee"}


async def test_hr_creates_employee_but_not_hr_or_admin(user_admin, make_user):
    hr = make_user(Role.HR_ADMIN)
    await user_admin.create_user(hr, email="emp2@x.hcm", password="pw123456", name="Emp Two",
                                 role="employee", department="Engineering", job_title="Eng")
    with pytest.raises(AccessDenied):
        await user_admin.create_user(hr, email="hr2@x.hcm", password="pw123456", name="HR Two",
                                     role="hr_admin", department="Engineering", job_title="HR")
    with pytest.raises(AccessDenied):
        await user_admin.create_user(hr, email="adm@x.hcm", password="pw123456", name="Adm",
                                     role="admin", department="Engineering", job_title="Boss")


async def test_employee_cannot_list_or_create(user_admin, make_user):
    emp = make_user(Role.EMPLOYEE)
    with pytest.raises(AccessDenied):
        await user_admin.list_users(emp)
    with pytest.raises(AccessDenied):
        await user_admin.create_user(emp, email="x@x.hcm", password="pw123456", name="X",
                                     role="employee", department="Engineering", job_title="Eng")


async def test_duplicate_email_rejected(user_admin, make_user):
    admin = make_user(Role.ADMIN)
    await user_admin.bootstrap_admin(email="root@demo.hcm", password="rootpass1", name="Root")
    await user_admin.create_user(admin, email="dup@x.hcm", password="pw123456", name="One",
                                 role="employee", department="Engineering", job_title="Eng")
    with pytest.raises(ValidationError) as exc:
        await user_admin.create_user(admin, email="dup@x.hcm", password="pw123456", name="Two",
                                     role="employee", department="Engineering", job_title="Eng")
    assert exc.value.field == "email"


async def test_short_password_rejected(user_admin, make_user):
    admin = make_user(Role.ADMIN)
    with pytest.raises(ValidationError) as exc:
        await user_admin.create_user(admin, email="p@x.hcm", password="short", name="P",
                                     role="employee", department="Engineering", job_title="Eng")
    assert exc.value.field == "password"


# --------------------------------------------------------------------------- update / delete


async def test_update_deactivate_delete_happy_path(user_admin, make_user, tmp_path):
    admin = make_user(Role.ADMIN)
    created = await user_admin.create_user(admin, email="mut@x.hcm", password="pw123456",
                                           name="Before", role="employee",
                                           department="Engineering", job_title="Eng")
    uid = created["user_id"]
    await user_admin.update_user(admin, uid, name="After", job_title="Senior Eng")
    await user_admin.set_active(admin, uid, False)
    row = _rows(tmp_path, "SELECT e.full_name, e.job_title, u.active FROM users u"
                          " JOIN employees e ON e.id = u.employee_id WHERE u.id=?", (uid,))
    assert row == [("After", "Senior Eng", 0)]
    await user_admin.delete_user(admin, uid)
    assert _rows(tmp_path, "SELECT id FROM users WHERE id=?", (uid,)) == []


async def test_self_management_blocked(user_admin, make_user):
    admin = make_user(Role.ADMIN)  # user_id U0004
    with pytest.raises(AccessDenied):
        await user_admin.delete_user(admin, admin.user_id)
    with pytest.raises(AccessDenied):
        await user_admin.set_active(admin, admin.user_id, False)


async def test_managing_an_admin_is_blocked(user_admin, make_user):
    admin = make_user(Role.ADMIN)
    await user_admin.bootstrap_admin(email="root@demo.hcm", password="rootpass1", name="Root")
    admin_id = await _admin_id(user_admin, admin)
    hr = make_user(Role.HR_ADMIN)
    with pytest.raises(AccessDenied):
        await user_admin.delete_user(hr, admin_id)
    with pytest.raises(AccessDenied):
        await user_admin.update_user(hr, admin_id, name="Hacked")


async def test_update_unknown_user_is_not_found(user_admin, make_user):
    admin = make_user(Role.ADMIN)
    with pytest.raises(NotFound):
        await user_admin.update_user(admin, "U9999", name="Ghost")
