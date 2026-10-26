"""TestClient harness for the setup/users routes.

Builds a small FastAPI app wired to the seeded temp SQLite DB with the real services and the
same exception-to-status mapping as ``hcm_lite.api.main``. No OpenAI/Qdrant lifespan runs, so
these tests stay offline. The engine is created lazily and first used inside the TestClient loop,
then disposed in a worker thread so no aiosqlite connection outlives the test.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from hcm_lite.assistant.context import Services
from hcm_lite.db.engine import create_engine, session_factory
from hcm_lite.errors import AccessDenied, NotFound, ValidationError
from hcm_lite.services.audit import Auditor
from hcm_lite.services.auth_service import AuthService
from hcm_lite.services.authz import Authz
from hcm_lite.services.passwords import hash_password
from hcm_lite.services.user_admin_service import UserAdminService
from tests.conftest import DEMO_PASSWORD


def _register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AccessDenied)
    async def _denied(_r: Request, exc: AccessDenied) -> JSONResponse:
        return JSONResponse(status_code=403,
                            content={"error": {"code": "access_denied"}})

    @app.exception_handler(ValidationError)
    async def _invalid(_r: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_input", "message": exc.message,
                               "field": exc.field}})

    @app.exception_handler(NotFound)
    async def _missing(_r: Request, _exc: NotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": {"code": "not_found"}})


@pytest.fixture
def api_client(settings, seeded_db) -> Iterator[TestClient]:
    from hcm_lite.api.routes import auth as auth_routes
    from hcm_lite.api.routes import setup as setup_routes
    from hcm_lite.api.routes import users as users_routes

    engine = create_engine(settings)
    sf = session_factory(engine)
    auditor = Auditor(sf)
    authz = Authz(sf, auditor)
    auth = AuthService.from_settings(settings, sf, auditor)
    user_admin = UserAdminService(sf, authz, auditor,
                                  hasher=lambda p: hash_password(p, iterations=1_000))

    app = FastAPI()
    app.state.services = Services(auth=auth, user_admin=user_admin)
    _register_handlers(app)
    app.include_router(auth_routes.router, prefix="/api/v1")
    app.include_router(setup_routes.router, prefix="/api/v1")
    app.include_router(users_routes.router, prefix="/api/v1")

    try:
        with TestClient(app) as client:
            yield client
    finally:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, engine.dispose()).result()


def token_for(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> str:
    response = client.post("/api/v1/auth/token",
                           data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> dict:
    return {"Authorization": f"Bearer {token_for(client, email, password)}"}
