"""Audit trail (research D-11, data-model.md audit_events, FR-034).

``Auditor.audit`` writes one ``audit_events`` row in its own short transaction and **never
raises** into callers: a failure is logged (event name and category only) and swallowed. Rows
carry no message text, document text, passwords or employee names.

The correlation id and channel of the current request/turn live in context variables, set by
the entry points (Chainlit handlers, FastAPI middleware).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from hcm_lite.db.repositories import AuditRepo
from hcm_lite.models.domain import AuditAction, AuditEventRecord, AuditOutcome, Channel

logger = logging.getLogger("hcm_lite.audit")

correlation_id_var: ContextVar[str | None] = ContextVar("hcm_correlation_id", default=None)
channel_var: ContextVar[Channel] = ContextVar("hcm_channel", default=Channel.CHAT)


def new_correlation_id() -> str:
    cid = str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid


def current_correlation_id() -> str:
    return correlation_id_var.get() or new_correlation_id()


class Auditor:
    def __init__(self, session_factory: Any, *, clock: Callable[[], datetime] | None = None
                 ) -> None:
        self._sf = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def audit(
        self,
        action: AuditAction | str,
        outcome: AuditOutcome | str,
        actor: str | None = None,
        target: str | None = None,
        channel: Channel | str | None = None,
    ) -> None:
        try:
            record = AuditEventRecord(
                at=self._clock(), actor_user_id=actor, action=AuditAction(action),
                channel=Channel(channel) if channel is not None else channel_var.get(),
                target=target, outcome=AuditOutcome(outcome),
                correlation_id=current_correlation_id(),
            )
            async with self._sf() as session, session.begin():
                await AuditRepo(session).insert(record)
        except Exception as exc:  # never raise into callers
            logger.warning("audit.write_failed",
                           extra={"category": getattr(exc, "category", "internal")})
