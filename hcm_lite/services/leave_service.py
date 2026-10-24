"""Leave service: self-only reads (US1/US4) and the smart-leave draft/submit flow (US5).

``my_balance`` and ``my_requests`` never take an employee id: identity comes only from the
``AuthenticatedUser``. ``remaining`` is computed as entitled − used − pending days; figures
come from SQL SUM/COUNT aggregations in the repository.

Part 2 (US5): ``build_draft`` validates and stores a DRAFT in the session's DraftStore and
never writes the database. ``submit`` re-validates, inserts exactly once via
``LeaveRepo.insert_idempotent`` (idempotency key = draft id) and audits only on first insert.
Submission is only reachable through the UI Confirm action or the API confirm endpoint —
there is no submit tool.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from hcm_lite.db.repositories import HolidayRepo, LeaveRepo
from hcm_lite.errors import NotFound, ValidationError
from hcm_lite.models.domain import (
    AuditOutcome,
    AuthenticatedUser,
    LeaveRequestRecord,
    LeaveSource,
    LeaveStatus,
    LeaveType,
)
from hcm_lite.models.requests import LeaveDraftRequest
from hcm_lite.models.results import (
    BalanceEntry,
    DraftStatus,
    LeaveBalanceResult,
    LeaveDraft,
    LeaveRequestItem,
    LeaveRequestList,
    ToolResult,
)
from hcm_lite.services.audit import Auditor
from hcm_lite.services.authz import Authz, Capability
from hcm_lite.services.periods import working_days as _working_days

__all__ = ["LeaveService"]


def _new_reference(today: date) -> str:
    return f"LR-{today:%Y%m%d}-{secrets.token_hex(2).upper()}"


class LeaveService:
    def __init__(self, session_factory: Any, authz: Authz, auditor: Auditor, *,
                 policy: Any = None, today: date | None = None) -> None:
        self._sf = session_factory
        self._authz = authz
        self._auditor = auditor
        self._policy = policy
        self._today_default = today

    def _today(self, today: date | None) -> date:
        return today or self._today_default or date.today()

    # ------------------------------------------------------------------ part 1: reads

    async def my_balance(self, user: AuthenticatedUser,
                         leave_type: str | LeaveType | None = None, *,
                         today: date | None = None) -> ToolResult[LeaveBalanceResult]:
        """The caller's own balances for the current year; remaining = entitled − used − pending."""
        await self._authz.require(user, Capability.OWN_DATA)
        if leave_type is not None:
            try:
                leave_type = LeaveType(leave_type)
            except ValueError:
                raise ValidationError("leave_type", "unknown leave type") from None
        as_of = self._today(today)
        async with self._sf() as session:
            leave = LeaveRepo(session)
            balances = await leave.balances_for(user.employee_id, as_of.year)
            pending = await leave.sum_days_by_type(
                employee_ids={user.employee_id}, start=date(as_of.year, 1, 1),
                end=date(as_of.year, 12, 31), statuses=(LeaveStatus.PENDING,))
        if leave_type is not None:
            balances = [b for b in balances if b.leave_type == leave_type]
        if not balances:
            return ToolResult.failure(
                "no_data", "No leave balances for this year",
                source="hr-db:leave_balances", scope="self")
        entries = [
            BalanceEntry(
                leave_type=b.leave_type, entitled=b.entitled, used=b.used,
                pending=Decimal(str(pending.get(b.leave_type.value, 0))),
                remaining=b.entitled - b.used - Decimal(str(pending.get(b.leave_type.value, 0))))
            for b in balances
        ]
        return ToolResult.success(
            LeaveBalanceResult(employee_id=user.employee_id, year=as_of.year, as_of=as_of,
                               balances=entries),
            source="hr-db:leave_balances", scope="self",
            is_demo=any(b.is_demo for b in balances))

    async def my_requests(
        self, user: AuthenticatedUser, limit: int = 10,
    ) -> ToolResult[LeaveRequestList]:
        """The caller's own leave requests, newest first (at most ``limit``, 1–50)."""
        await self._authz.require(user, Capability.OWN_DATA)
        if not 1 <= limit <= 50:
            raise ValidationError("limit", "must be between 1 and 50")
        async with self._sf() as session:
            rows = await LeaveRepo(session).list_for_employees(
                employee_ids={user.employee_id}, limit=limit)
        if not rows:
            return ToolResult.failure(
                "no_data", "No leave requests",
                source="hr-db:leave_requests", scope="self")
        return ToolResult.success(
            LeaveRequestList(
                count=len(rows),
                requests=[
                    LeaveRequestItem(reference=r.id, leave_type=r.leave_type,
                                     start_date=r.start_date, end_date=r.end_date,
                                     working_days=r.working_days, status=r.status,
                                     created_at=r.created_at)
                    for r in rows]),
            source="hr-db:leave_requests", scope="self",
            is_demo=any(r.is_demo for r in rows))

    # ------------------------------------------------------------------ part 2: drafts

    async def build_draft(
        self,
        user: AuthenticatedUser,
        store: Any,  # DraftStore
        request: LeaveDraftRequest,
        *,
        today: date | None = None,
    ) -> ToolResult[LeaveDraft]:
        """Validate and store a leave DRAFT in the session's store. Never writes the DB."""
        await self._authz.require(user, Capability.LEAVE_SELF)
        as_of = self._today(today)

        existing = store.get_draft(request.draft_id) if request.draft_id else None
        if request.draft_id and existing is None:
            raise NotFound("draft")

        base = existing or LeaveDraft(draft_id=str(uuid.uuid4()))
        updates: dict[str, Any] = {}
        if request.leave_type is not None:
            updates["leave_type"] = request.leave_type
        if request.start_date is not None:
            updates["start_date"] = request.start_date
        if request.end_date is not None:
            updates["end_date"] = request.end_date
        if request.reason is not None:
            updates["reason"] = request.reason
        draft = base.model_copy(update=updates) if updates else base

        missing = [field for field, value in (
            ("leave_type", draft.leave_type), ("start_date", draft.start_date),
            ("end_date", draft.end_date)) if value is None]
        errors: list[str] = []
        warnings: list[str] = []
        citations: list[Any] = []
        working: int | None = None
        remaining: Decimal | None = None

        if not missing:
            start, end = draft.start_date, draft.end_date
            if end < start:
                errors.append("end_date is before start_date")
            elif start < as_of:
                errors.append("the leave starts in the past")
            elif (end - start).days > 60:
                errors.append("the requested span exceeds 60 days")
            else:
                async with self._sf() as session:
                    holidays = [h.date for h in await HolidayRepo(session).between(start, end)]
                    overlaps = await LeaveRepo(session).list_for_employees(
                        employee_ids={user.employee_id}, limit=50)
                    balances = await LeaveRepo(session).balances_for(
                        user.employee_id, as_of.year)
                    pending = await LeaveRepo(session).sum_days_by_type(
                        employee_ids={user.employee_id}, start=date(as_of.year, 1, 1),
                        end=date(as_of.year, 12, 31), statuses=(LeaveStatus.PENDING,))
                working = _working_days(start, end, holidays)
                if working == 0:
                    errors.append("the range contains no working days")
                if any(r.status in (LeaveStatus.PENDING, LeaveStatus.APPROVED)
                       and r.start_date <= end and start <= r.end_date for r in overlaps):
                    errors.append("the dates overlap an existing leave request")
                entry = next((b for b in balances if b.leave_type == draft.leave_type), None)
                if entry is not None:
                    pending_days = Decimal(str(pending.get(draft.leave_type.value, 0)))
                    remaining = entry.entitled - entry.used - pending_days
                    if working and Decimal(working) > remaining:
                        warnings.append(
                            f"this request exceeds the remaining balance "
                            f"({remaining} day(s) left)")
                if self._policy is not None and not errors:
                    policy = await self._policy.search(
                        user, f"{draft.leave_type.value} leave policy rules")
                    if policy.ok and policy.data is not None and policy.data.found:
                        citations = [chunk.citation for chunk in policy.data.chunks[:2]]

        status = (DraftStatus.INCOMPLETE if missing
                  else DraftStatus.INVALID if errors
                  else DraftStatus.READY_FOR_REVIEW)
        draft = draft.model_copy(update={
            "status": status, "working_days": working, "missing_fields": missing,
            "validation_errors": errors, "warnings": warnings,
            "balance_remaining": remaining, "policy_citations": citations})
        store.put_draft(draft)
        return ToolResult.success(
            draft, source="hr-db:leave_balances", scope="self", is_demo=True)

    async def submit(
        self,
        user: AuthenticatedUser,
        store: Any,  # DraftStore
        draft_id: str,
        *,
        channel: str = "chat",
        today: date | None = None,
    ) -> LeaveRequestRecord:
        """Submit a ready draft exactly once (idempotent by ``draft_id``); audit on first insert."""
        await self._authz.require(user, Capability.LEAVE_SELF)
        as_of = self._today(today)
        draft = store.get_draft(draft_id)
        if draft is None:
            raise NotFound("draft")

        async with self._sf() as session:
            leave = LeaveRepo(session)
            existing = await leave.get_by_idempotency_key(draft_id)
            if existing is not None:
                record, created = existing, False
            else:
                recheck = await self.build_draft(
                    user, store,
                    LeaveDraftRequest(leave_type=draft.leave_type,
                                      start_date=draft.start_date,
                                      end_date=draft.end_date, reason=draft.reason,
                                      draft_id=draft.draft_id),
                    today=as_of)
                if not recheck.ok or recheck.data.status != DraftStatus.READY_FOR_REVIEW:
                    raise ValidationError("draft", "the draft is no longer valid")
                fresh = recheck.data
                record = LeaveRequestRecord(
                    id=_new_reference(as_of), employee_id=user.employee_id,
                    leave_type=fresh.leave_type, start_date=fresh.start_date,
                    end_date=fresh.end_date, working_days=fresh.working_days or 1,
                    reason=fresh.reason or "", status=LeaveStatus.PENDING,
                    source=LeaveSource.API if channel == "api" else LeaveSource.ASSISTANT,
                    idempotency_key=draft_id, created_by=user.user_id,
                    created_at=datetime.now(timezone.utc), is_demo=True)
                record, created = await leave.insert_idempotent(record)
                await session.commit()
        if created:
            await self._auditor.audit("leave_submitted", AuditOutcome.OK,
                                      actor=user.user_id, target=record.id, channel=channel)
        store.put_draft(draft.model_copy(update={
            "status": DraftStatus.SUBMITTED, "submitted_reference": record.id}))
        return record
