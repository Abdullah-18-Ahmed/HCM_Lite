"""Validated request models shared by agent tools and API routes. All use extra="forbid";
none carries a role or a user/employee id (identity comes from ``AuthenticatedUser``)."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from hcm_lite.models.domain import (
    PERIOD_KEYWORDS,
    YEAR_MONTH_PATTERN,
    EmploymentStatus,
    LeaveType,
)

_YEAR_MONTH = re.compile(YEAR_MONTH_PATTERN)


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PeriodArgs(_Request):
    period: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("period")
    @classmethod
    def _known_period(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if value not in PERIOD_KEYWORDS and not _YEAR_MONTH.match(value):
            raise ValueError(f"must be one of {', '.join(PERIOD_KEYWORDS)} or YYYY-MM")
        return value

    @model_validator(mode="after")
    def _both_bounds(self) -> PeriodArgs:
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("start_date and end_date must be given together")
        return self


class DepartmentFilter(_Request):
    department: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None

    @field_validator("department", mode="before")
    @classmethod
    def _blank(cls, value: object) -> object:
        return _blank_to_none(value)


class EmployeeSearchFilters(_Request):
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    department: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    job_title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    status: EmploymentStatus | None = None

    @field_validator("name", "department", "job_title", mode="before")
    @classmethod
    def _blank(cls, value: object) -> object:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _at_least_one(self) -> EmployeeSearchFilters:
        if all(v is None for v in (self.name, self.department, self.job_title, self.status)):
            raise ValueError("give at least one of name, department, job_title or status")
        return self


class PolicyQuery(_Request):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
    doc_type: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None


class LeaveDraftRequest(_Request):
    leave_type: LeaveType | None = None
    start_date: date | None = None
    end_date: date | None = None
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    draft_id: str | None = None

    @field_validator("draft_id")
    @classmethod
    def _uuid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(uuid.UUID(value))
        except ValueError:
            raise ValueError("must be a draft id returned earlier") from None


class ChatMessage(_Request):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
