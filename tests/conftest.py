"""Shared fixtures (T041): real temp SQLite DBs migrated with Alembic, a seeded copy per test,
a frozen clock, dummy settings, users, run contexts, a hashing embedder and ``ScriptedModel``.

Alembic's async ``env.py`` calls ``asyncio.run``, so Alembic commands (and the one-off seed of
the template DB) run in a worker thread. Every engine is disposed so no aiosqlite thread or open
file handle outlives the test (Windows cannot delete open files).
"""

from __future__ import annotations

import asyncio
import shutil
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from typing import Any

import pytest

from hcm_lite.assistant.context import AppContext, AppSession, Services
from hcm_lite.config import Settings, load_settings
from hcm_lite.db.engine import alembic_config, create_engine, create_engine_for_url, session_factory
from hcm_lite.models.domain import AuthenticatedUser, Role
from tests.fakes.embedder import HashingEmbedder
from tests.fakes.scripted_model import ScriptedModel, ToolCall

__all__ = ["DEMO_PASSWORD", "FROZEN_NOW", "TODAY", "HashingEmbedder", "ScriptedModel",
           "ToolCall", "run_alembic", "test_run_config"]

TODAY = date(2026, 10, 25)  # a Sunday
FROZEN_NOW = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
DEMO_PASSWORD = "Demo-Pass-123"  # test-only; real seeds generate random passwords

REQUIRED_ENV = {
    "OPENAI_API_KEY": "sk-test-not-a-real-key",
    "OPENAI_MODEL": "gpt-test",
    "OPENAI_EMBEDDING_MODEL": "text-embedding-test",
    "API_JWT_SECRET": "t" * 48,
}

# Demo users created by the seed (research D-13). (user id, username, employee id, email)
DEMO_USERS = {
    Role.EMPLOYEE: ("U0001", "employee", "E1001", "employee@demo.hcm"),
    Role.MANAGER: ("U0002", "manager", "M1002", "manager@demo.hcm"),
    Role.HR_ADMIN: ("U0003", "hr_admin", "H1003", "hr_admin@demo.hcm"),
    # Not created by the seed; used only to build an admin AuthenticatedUser in tests.
    # A high id avoids colliding with the ``U0004+`` ids allocated to created accounts.
    Role.ADMIN: ("U9001", "admin", "A9001", "admin@demo.hcm"),
}


def run_alembic(command: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run an ``alembic.command`` function in a worker thread (env.py uses asyncio.run)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(command, *args, **kwargs).result()


def test_run_config() -> Any:
    from agents import RunConfig

    return RunConfig(tracing_disabled=True)


test_run_config.__test__ = False  # not a test


class Clock:
    def __init__(self, now: datetime = FROZEN_NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: Any) -> None:
        from datetime import timedelta

        self.now += timedelta(**kwargs)


# --------------------------------------------------------------------------- guards


@pytest.fixture(autouse=True)
def no_leaked_threads() -> Iterator[None]:
    """Fail a test that leaves aiosqlite worker threads running (an engine not disposed)."""
    before = set(threading.enumerate())
    yield
    deadline = time.monotonic() + 2.0
    while True:
        leaked = [t for t in threading.enumerate()
                  if t not in before and t.is_alive() and "_connection_worker" in t.name]
        if not leaked or time.monotonic() > deadline:
            break
        time.sleep(0.02)
    assert not leaked, f"threads left running: {[t.name for t in leaked]}"


# --------------------------------------------------------------------------- clock / settings


@pytest.fixture
def frozen_today() -> date:
    return TODAY


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def db_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / 'hcm_test.db').as_posix()}"


@pytest.fixture
def settings(monkeypatch, tmp_path, db_url) -> Settings:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path))
    return load_settings(env_file=None)


# --------------------------------------------------------------------------- databases


@pytest.fixture
def alembic_cfg(db_url):
    return alembic_config(db_url)


@pytest.fixture
def migrated_db(alembic_cfg, db_url) -> str:
    from alembic import command

    run_alembic(command.upgrade, alembic_cfg, "head")
    return db_url


def _build_seed_template(path) -> None:
    from alembic import command

    from hcm_lite.db.seed import run_seed
    from hcm_lite.services.passwords import hash_password

    url = f"sqlite+aiosqlite:///{path.as_posix()}"
    run_alembic(command.upgrade, alembic_config(url), "head")

    async def _seed() -> None:
        engine = create_engine_for_url(url)
        try:
            await run_seed(engine, today=TODAY, password_factory=lambda: DEMO_PASSWORD,
                           hasher=lambda p: hash_password(p, iterations=1_000), now=FROZEN_NOW)
        finally:
            await engine.dispose()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, _seed()).result()


@pytest.fixture(scope="session")
def seed_template(tmp_path_factory):
    path = tmp_path_factory.mktemp("seed") / "template.db"
    _build_seed_template(path)
    return path


@pytest.fixture
def seeded_db(seed_template, tmp_path, db_url) -> str:
    """A private copy of the seeded template DB (fast: one seed per test session)."""
    target = tmp_path / "hcm_test.db"
    shutil.copyfile(seed_template, target)
    for suffix in ("-wal", "-shm"):
        side = seed_template.with_name(seed_template.name + suffix)
        if side.exists():
            shutil.copyfile(side, target.with_name(target.name + suffix))
    return db_url


@pytest.fixture
async def engine(settings) -> AsyncIterator[Any]:
    eng = create_engine(settings)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
async def session(migrated_db, engine) -> AsyncIterator[Any]:
    factory = session_factory(engine)
    async with factory() as s:
        yield s
        await s.rollback()


@pytest.fixture
def sf(seeded_db, engine):
    """Session factory on the seeded copy (services open and commit their own sessions)."""
    return session_factory(engine)


# --------------------------------------------------------------------------- users, services


@pytest.fixture
def make_user() -> Callable[..., AuthenticatedUser]:
    def _make(role: Role | str = Role.EMPLOYEE, employee_id: str | None = None,
              **overrides: Any) -> AuthenticatedUser:
        role = Role(role)
        uid, username, eid, email = DEMO_USERS[role]
        data = dict(user_id=uid, username=username, email=email, role=role,
                    employee_id=employee_id or eid, display_name="Demo User",
                    department="Engineering")
        data.update(overrides)
        return AuthenticatedUser(**data)

    return _make


@pytest.fixture
def auditor(sf, clock):
    from hcm_lite.services.audit import Auditor

    return Auditor(sf, clock=clock)


@pytest.fixture
def authz(sf, auditor):
    from hcm_lite.services.authz import Authz

    return Authz(sf, auditor)


@pytest.fixture
def auth_service(sf, auditor, settings, clock):
    from hcm_lite.services.auth_service import AuthService

    return AuthService.from_settings(settings, sf, auditor, clock=clock)


@pytest.fixture
def services(settings, sf, auditor, authz, auth_service) -> Services:
    """The service container used by tools, the runner and UI handlers."""
    return build_test_services(settings, sf, auditor, authz, auth_service)


def build_test_services(settings, sf, auditor, authz, auth_service) -> Services:
    svc = Services(auth=auth_service, run_config=test_run_config(),
                   max_turns=settings.agent_max_turns)
    try:
        from hcm_lite.services.metrics_service import MetricsService

        svc.metrics = MetricsService(sf, authz, late_grace_minutes=settings.late_grace_minutes)
    except ImportError:
        pass
    try:
        from hcm_lite.services.leave_service import LeaveService

        svc.leave = LeaveService(sf, authz, auditor)
    except ImportError:
        pass
    try:
        from hcm_lite.services.dashboard_service import DashboardService

        if svc.metrics is not None and svc.leave is not None:
            svc.dashboard = DashboardService(svc.metrics, svc.leave)
    except ImportError:
        pass
    try:
        from hcm_lite.services.user_admin_service import UserAdminService

        svc.user_admin = UserAdminService(sf, authz, auditor)
    except ImportError:
        pass
    return svc


@pytest.fixture
def make_ctx(services, make_user, frozen_today, settings) -> Callable[..., AppContext]:
    def _make(role: Role | str = Role.EMPLOYEE, *, user: AuthenticatedUser | None = None,
              model: Any = None, tools: list | None = None) -> AppContext:
        user = user or make_user(role)
        if model is not None:
            from hcm_lite.assistant.hr_agent import build_agent
            from hcm_lite.assistant.tools import TOOLS

            services.agent = build_agent(settings, TOOLS if tools is None else tools,
                                         model=model)
        return AppContext(user=user, session=AppSession(user=user), today=frozen_today,
                          services=services)

    return _make


@pytest.fixture
def tool_ctx(make_ctx):
    """``RunContextWrapper`` factory for calling tools directly."""
    from agents import RunContextWrapper

    def _make(role: Role | str = Role.EMPLOYEE, **kwargs: Any) -> Any:
        return RunContextWrapper(context=make_ctx(role, **kwargs))

    return _make


@pytest.fixture
def hashing_embedder() -> HashingEmbedder:
    return HashingEmbedder()
