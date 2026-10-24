"""Shared fixtures for the US1 service tests (T046–T048).

Builds the Metrics/Leave/Dashboard services on the seeded temp DB with the frozen ``today``
(T041 fixtures) and offers a direct-SQL helper so every expected figure is derived
independently of the service under test (SC-002).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from tests.conftest import TODAY


def sql_all(tmp_path, sql: str, params: tuple = ()) -> list[tuple]:
    """Read rows straight from the seeded SQLite file (WAL readers are fine)."""
    with closing(sqlite3.connect(tmp_path / "hcm_test.db")) as db:
        return db.execute(sql, params).fetchall()


def sql_one(tmp_path, sql: str, params: tuple = ()):
    return sql_all(tmp_path, sql, params)[0][0]


def team_ids(tmp_path, manager_id: str = "M1002") -> set[str]:
    """The manager's resolved scope: self plus direct reports."""
    rows = sql_all(tmp_path, "SELECT id FROM employees WHERE id = ? OR manager_id = ?",
                   (manager_id, manager_id))
    return {r[0] for r in rows}


@pytest.fixture
def metrics(sf, authz):
    from hcm_lite.services.metrics_service import MetricsService

    return MetricsService(sf, authz, late_grace_minutes=0, today=TODAY)


@pytest.fixture
def make_metrics(sf, authz):
    """MetricsService variants (e.g. a different late grace)."""

    def _make(**kwargs) -> "object":
        from hcm_lite.services.metrics_service import MetricsService

        kwargs.setdefault("today", TODAY)
        kwargs.setdefault("late_grace_minutes", 0)
        return MetricsService(sf, authz, **kwargs)

    return _make


@pytest.fixture
def leave(sf, authz, auditor):
    from hcm_lite.services.leave_service import LeaveService

    return LeaveService(sf, authz, auditor, today=TODAY)


@pytest.fixture
def dashboard(metrics, leave):
    from hcm_lite.services.dashboard_service import DashboardService

    return DashboardService(metrics, leave)
