"""User-administration routes via TestClient on the seeded DB."""

from __future__ import annotations

from tests.unit.api.conftest import auth_header

ADMIN = {"email": "root@demo.hcm", "password": "rootpass1", "name": "Root Admin"}
ADMIN_LOGIN = (ADMIN["email"], ADMIN["password"])


def _bootstrap_admin(api_client) -> dict:
    assert api_client.post("/api/v1/setup/admin", json=ADMIN).status_code == 201
    return auth_header(api_client, *ADMIN_LOGIN)


def _new_user(role="employee", **over) -> dict:
    body = {"email": "new@x.hcm", "password": "pw123456", "name": "New Person",
            "role": role, "department": "Engineering", "job_title": "Engineer"}
    body.update(over)
    return body


# --------------------------------------------------------------------------- listing


def test_admin_lists_all_users(api_client):
    headers = _bootstrap_admin(api_client)
    response = api_client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200
    users = response.json()["users"]
    roles = {u["role"] for u in users}
    assert "admin" in roles and "employee" in roles
    sample = users[0]
    assert set(sample) == {"user_id", "email", "name", "role", "department", "job_title",
                           "active", "created_at"}


def test_hr_lists_only_employees(api_client):
    _bootstrap_admin(api_client)
    headers = auth_header(api_client, "hr_admin@demo.hcm")
    users = api_client.get("/api/v1/users", headers=headers).json()["users"]
    assert users and {u["role"] for u in users} == {"employee"}


def test_employee_cannot_list(api_client):
    _bootstrap_admin(api_client)
    headers = auth_header(api_client, "employee@demo.hcm")
    assert api_client.get("/api/v1/users", headers=headers).status_code == 403


# --------------------------------------------------------------------------- create


def test_admin_creates_hr_and_employee(api_client):
    headers = _bootstrap_admin(api_client)
    hr = api_client.post("/api/v1/users", headers=headers,
                         json=_new_user(role="hr_admin", email="hr1@x.hcm"))
    assert hr.status_code == 201 and hr.json()["user_id"].startswith("U")
    emp = api_client.post("/api/v1/users", headers=headers,
                          json=_new_user(role="employee", email="emp1@x.hcm"))
    assert emp.status_code == 201


def test_hr_creates_employee_but_not_hr(api_client):
    _bootstrap_admin(api_client)
    headers = auth_header(api_client, "hr_admin@demo.hcm")
    ok = api_client.post("/api/v1/users", headers=headers,
                         json=_new_user(role="employee", email="emp2@x.hcm"))
    assert ok.status_code == 201
    denied = api_client.post("/api/v1/users", headers=headers,
                             json=_new_user(role="hr_admin", email="hr2@x.hcm"))
    assert denied.status_code == 403


def test_employee_cannot_create(api_client):
    _bootstrap_admin(api_client)
    headers = auth_header(api_client, "employee@demo.hcm")
    response = api_client.post("/api/v1/users", headers=headers,
                               json=_new_user(email="nope@x.hcm"))
    assert response.status_code == 403


def test_duplicate_email_is_422(api_client):
    headers = _bootstrap_admin(api_client)
    first = api_client.post("/api/v1/users", headers=headers, json=_new_user(email="dup@x.hcm"))
    assert first.status_code == 201
    second = api_client.post("/api/v1/users", headers=headers, json=_new_user(email="dup@x.hcm"))
    assert second.status_code == 422
    assert second.json()["error"]["field"] == "email"


# --------------------------------------------------------------------------- update / delete


def test_update_deactivate_delete(api_client):
    headers = _bootstrap_admin(api_client)
    uid = api_client.post("/api/v1/users", headers=headers,
                          json=_new_user(email="mut@x.hcm")).json()["user_id"]

    patched = api_client.patch(f"/api/v1/users/{uid}", headers=headers,
                               json={"name": "Renamed", "job_title": "Senior"})
    assert patched.status_code == 200 and patched.json() == {"ok": True}

    deactivated = api_client.post(f"/api/v1/users/{uid}/active", headers=headers,
                                  json={"active": False})
    assert deactivated.status_code == 200

    deleted = api_client.delete(f"/api/v1/users/{uid}", headers=headers)
    assert deleted.status_code == 204
    remaining = {u["user_id"] for u in api_client.get("/api/v1/users", headers=headers)
                 .json()["users"]}
    assert uid not in remaining


def test_admin_cannot_delete_self(api_client):
    headers = _bootstrap_admin(api_client)
    users = api_client.get("/api/v1/users", headers=headers).json()["users"]
    admin_id = next(u["user_id"] for u in users if u["role"] == "admin")
    assert api_client.delete(f"/api/v1/users/{admin_id}", headers=headers).status_code == 403


def test_hr_cannot_manage_admin(api_client):
    admin_headers = _bootstrap_admin(api_client)
    users = api_client.get("/api/v1/users", headers=admin_headers).json()["users"]
    admin_id = next(u["user_id"] for u in users if u["role"] == "admin")
    hr_headers = auth_header(api_client, "hr_admin@demo.hcm")
    assert api_client.delete(f"/api/v1/users/{admin_id}", headers=hr_headers).status_code == 403


# --------------------------------------------------------------------------- password change


def test_password_change_happy_then_login(api_client):
    _bootstrap_admin(api_client)
    headers = auth_header(api_client, "employee@demo.hcm")
    response = api_client.post("/api/v1/me/password", headers=headers,
                               json={"old_password": "Demo-Pass-123",
                                     "new_password": "brand-new-9"})
    assert response.status_code == 204
    # the new password now authenticates; the old one no longer does
    assert token_ok(api_client, "employee@demo.hcm", "brand-new-9")
    assert not token_ok(api_client, "employee@demo.hcm", "Demo-Pass-123")


def test_password_change_wrong_old_is_422(api_client):
    _bootstrap_admin(api_client)
    headers = auth_header(api_client, "employee@demo.hcm")
    response = api_client.post("/api/v1/me/password", headers=headers,
                               json={"old_password": "wrong-pass", "new_password": "brand-new-9"})
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "old_password"


def test_password_change_too_short_is_422(api_client):
    _bootstrap_admin(api_client)
    headers = auth_header(api_client, "employee@demo.hcm")
    response = api_client.post("/api/v1/me/password", headers=headers,
                               json={"old_password": "Demo-Pass-123", "new_password": "short"})
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "new_password"


def test_requires_authentication(api_client):
    assert api_client.get("/api/v1/users").status_code == 401


def token_ok(client, email, password) -> bool:
    return client.post("/api/v1/auth/token",
                       data={"username": email, "password": password}).status_code == 200
