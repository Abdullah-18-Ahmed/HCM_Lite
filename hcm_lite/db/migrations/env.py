"""Alembic environment (async template; research D-03, constitution Art. IX.1.3).

The URL comes from ``config.attributes["database_url"]`` when the ``Config`` is built in code
(``hcm_lite.db.engine.alembic_config``), otherwise from ``get_settings().database_url``. No URL
lives in ``alembic.ini``. ``render_as_batch=True`` lets SQLite alter tables in later revisions.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from hcm_lite.db.engine import ensure_sqlite_folder
from hcm_lite.db.tables import HAND_MANAGED_INDEXES, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    url = config.attributes.get("database_url")
    if url:
        return url
    from hcm_lite.config import get_settings

    return get_settings().database_url.get_secret_value()


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    return not (type_ == "index" and name in HAND_MANAGED_INDEXES)


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        include_object=_include_object,
        render_as_batch=True,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = _database_url()
    ensure_sqlite_folder(url)
    connectable = create_async_engine(url, poolclass=pool.NullPool)
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
