"""Async SQLAlchemy engine for SQLite (research D-02, constitution Art. IX.1.1).

A sync ``"connect"`` listener sets ``foreign_keys=ON``, ``journal_mode=WAL`` and
``busy_timeout=5000`` on every connection. It also switches the driver to autocommit mode and a
``"begin"`` listener emits ``BEGIN`` itself: without that, the sqlite3 driver does not open a
transaction before a SAVEPOINT, and a "rolled back" transaction that started with a SAVEPOINT
is committed anyway (verified in research.md, Phase 2 batch B).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine

from hcm_lite.config import Settings
from hcm_lite.errors import ConfigurationError, DatabaseError

__all__ = [
    "MIGRATIONS_DIR", "OUT_OF_DATE_MESSAGE", "alembic_config", "assert_at_head",
    "create_engine", "create_engine_for_url", "current_revision", "dispose",
    "ensure_sqlite_folder",
    "head_revision", "session_factory",
]

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
OUT_OF_DATE_MESSAGE = "Database schema is out of date — run alembic upgrade head"
BUSY_TIMEOUT_MS = 5000


def _sqlite_file(url: str) -> Path | None:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return None
    database = parsed.database or ""
    if database in ("", ":memory:") or database.startswith("file:"):
        return None
    return Path(database)


def _install_sqlite_listeners(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None  # SQLAlchemy controls BEGIN (see module doc)
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN")


def ensure_sqlite_folder(url: str) -> None:
    """For a SQLite file URL, create the file's folder (e.g. ``data/``) if missing."""
    path = _sqlite_file(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)


def create_engine_for_url(url: str) -> AsyncEngine:
    """Create the async engine (and the SQLite folder) with the connection listeners."""
    ensure_sqlite_folder(url)
    engine = _create_async_engine(url)
    if engine.dialect.name == "sqlite":
        _install_sqlite_listeners(engine)
    return engine


def create_engine(settings: Settings) -> AsyncEngine:
    return create_engine_for_url(settings.database_url.get_secret_value())


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def dispose(engine: AsyncEngine) -> None:
    await engine.dispose()


# --------------------------------------------------------------------------- Alembic


def alembic_config(database_url: str | None = None) -> Config:
    """An Alembic ``Config`` built in code (no ini file, no URL in any file).

    ``env.py`` uses ``database_url`` from ``config.attributes`` when given, otherwise
    ``get_settings().database_url``.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    if database_url is not None:
        cfg.attributes["database_url"] = database_url
    return cfg


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


async def current_revision(engine: AsyncEngine) -> str | None:
    """The revision recorded in ``alembic_version`` (None for an unmigrated DB)."""
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: MigrationContext.configure(sync_conn).get_current_revision()
            )
    except DBAPIError:
        raise DatabaseError("The HR database could not be opened") from None


async def assert_at_head(engine: AsyncEngine) -> None:
    """Fail clearly at startup unless the DB is at the latest migration (Art. IX.1.1)."""
    if await current_revision(engine) != head_revision():
        raise ConfigurationError(OUT_OF_DATE_MESSAGE, variables=["DATABASE_URL"])


async def ping(engine: Any) -> bool:
    """``SELECT 1`` for health probes (sqlalchemy stays inside the db package)."""
    from sqlalchemy import text

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
