"""In-memory API conversations (US8 T092, contracts/api.md).

Each ``ApiConversation`` implements the ``DraftStore`` protocol and keeps the runner history,
keyed by ``(user_id, conversation_id)`` with an idle TTL of ``SESSION_IDLE_MINUTES``.
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from typing import Any

MAX_DRAFTS = 5


class ApiConversation:
    def __init__(self, user_id: str, idle_minutes: int) -> None:
        self.user_id = user_id
        self.history: list[Any] = []
        self.drafts: OrderedDict[str, Any] = OrderedDict()
        self.last_activity = time.monotonic()
        self._ttl = idle_minutes * 60

    # ------------------------------------------------------------------ DraftStore

    def get_draft(self, draft_id: str) -> Any | None:
        return self.drafts.get(draft_id)

    def put_draft(self, draft: Any) -> None:
        self.drafts[draft.draft_id] = draft
        self.drafts.move_to_end(draft.draft_id)
        while len(self.drafts) > MAX_DRAFTS:
            self.drafts.popitem(last=False)

    def discard_draft(self, draft_id: str) -> None:
        self.drafts.pop(draft_id, None)

    # ------------------------------------------------------------------ lifecycle

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def is_expired(self) -> bool:
        return time.monotonic() - self.last_activity > self._ttl


class ConversationStore:
    def __init__(self, idle_minutes: int) -> None:
        self._idle_minutes = idle_minutes
        self._conversations: dict[tuple[str, str], ApiConversation] = {}

    def create(self, user_id: str) -> str:
        self._sweep()
        cid = str(uuid.uuid4())
        self._conversations[(user_id, cid)] = ApiConversation(user_id, self._idle_minutes)
        return cid

    def get(self, user_id: str, cid: str) -> ApiConversation | None:
        conversation = self._conversations.get((user_id, cid))
        if conversation is None:
            return None
        if conversation.is_expired():
            self._conversations.pop((user_id, cid), None)
            return None
        return conversation

    def _sweep(self) -> None:
        for key, conversation in list(self._conversations.items()):
            if conversation.is_expired():
                self._conversations.pop(key, None)
