"""Run context and per-conversation session (data-model.md §2, contracts/services.md).

``AppSession`` is the Chainlit-side conversation state; it implements ``DraftStore`` so
``LeaveService.build_draft`` / ``submit`` work the same for Chainlit and the API.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from hcm_lite.models.domain import AuthenticatedUser
from hcm_lite.models.results import LeaveDraft

MAX_DRAFTS = 5


@runtime_checkable
class DraftStore(Protocol):
    def get_draft(self, draft_id: str) -> LeaveDraft | None: ...

    def put_draft(self, draft: LeaveDraft) -> None: ...

    def discard_draft(self, draft_id: str) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class AppSession:
    user: AuthenticatedUser
    idle_minutes: int = 60
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    history: list[Any] = field(default_factory=list)
    drafts: OrderedDict[str, LeaveDraft] = field(default_factory=OrderedDict)
    last_activity: datetime = field(default_factory=_utc_now)

    # ---------------------------------------------------------------- DraftStore
    def get_draft(self, draft_id: str) -> LeaveDraft | None:
        return self.drafts.get(draft_id)

    def put_draft(self, draft: LeaveDraft) -> None:
        self.drafts[draft.draft_id] = draft
        self.drafts.move_to_end(draft.draft_id)
        while len(self.drafts) > MAX_DRAFTS:
            self.drafts.popitem(last=False)  # evict the oldest

    def discard_draft(self, draft_id: str) -> None:
        self.drafts.pop(draft_id, None)

    # ---------------------------------------------------------------- idle tracking
    def is_idle(self, now: datetime | None = None) -> bool:
        now = now or _utc_now()
        return now - self.last_activity > timedelta(minutes=self.idle_minutes)

    def touch(self, now: datetime | None = None) -> None:
        self.last_activity = now or _utc_now()


@dataclass
class Services:
    """Everything a turn or a UI handler needs, built once per process."""

    auth: Any = None
    metrics: Any = None
    leave: Any = None
    policy: Any = None
    dashboard: Any = None
    agent: Any = None  # agents.Agent[AppContext]
    run_config: Any = None  # agents.RunConfig (tracing disabled)
    max_turns: int = 8


@dataclass
class AppContext:
    user: AuthenticatedUser
    session: DraftStore
    today: date
    services: Services
    demo_mode: bool = True
