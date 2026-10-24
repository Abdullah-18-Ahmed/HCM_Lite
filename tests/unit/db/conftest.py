"""DB-test guard. The shared DB fixtures (``db_url``, ``migrated_db``, ``engine``, ``session``,
``settings``, ...) live in ``tests/conftest.py``. Here every test fails if it leaves *any* new
thread running (an engine not disposed leaves an aiosqlite worker and an open file)."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def no_leaked_threads() -> Iterator[None]:
    before = set(threading.enumerate())
    yield
    deadline = time.monotonic() + 2.0
    while True:
        leaked = [t for t in threading.enumerate() if t not in before and t.is_alive()]
        if not leaked or time.monotonic() > deadline:
            break
        time.sleep(0.02)
    assert not leaked, f"threads left running: {[t.name for t in leaked]}"
