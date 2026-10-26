"""Setup routes: first-admin bootstrap (no auth)."""

from __future__ import annotations

ADMIN = {"email": "root@demo.hcm", "password": "rootpass1", "name": "Root Admin"}


def test_status_needs_admin_on_a_fresh_db(api_client):
    response = api_client.get("/api/v1/setup/status")
    assert response.status_code == 200
    assert response.json() == {"needs_admin": True}


def test_bootstrap_then_status_and_second_attempt(api_client):
    created = api_client.post("/api/v1/setup/admin", json=ADMIN)
    assert created.status_code == 201
    assert created.json() == {"ok": True}

    assert api_client.get("/api/v1/setup/status").json() == {"needs_admin": False}

    again = api_client.post("/api/v1/setup/admin", json=ADMIN)
    assert again.status_code == 409
    assert again.json() == {"error": {"code": "already_initialised"}}


def test_bootstrap_rejects_short_password(api_client):
    response = api_client.post("/api/v1/setup/admin",
                               json={"email": "a@demo.hcm", "password": "short", "name": "A"})
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "password"
