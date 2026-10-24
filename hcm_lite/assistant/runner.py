"""One chat turn, independent of Chainlit (contracts/agent-tools.md "Runner contract").

Used by Chainlit (``app.py``) and the API conversations endpoint. Errors are mapped to a fixed
category and a fixed user message; exception text never reaches the user.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import openai
from agents import (
    InputGuardrailTripwireTriggered,
    MaxTurnsExceeded,
    ModelBehaviorError,
    OutputGuardrailTripwireTriggered,
    Runner,
    UserError,
)

from hcm_lite.assistant.context import AppContext
from hcm_lite.errors import (
    ConfigurationError,
    DatabaseError,
    HCMError,
    ModelServiceError,
    RetrievalError,
)
from hcm_lite.models.results import Citation, DraftStatus, LeaveDraft

logger = logging.getLogger("hcm_lite.runner")

POLICY_TOOL = "search_hr_documents"
DRAFT_TOOL = "prepare_leave_draft"

ERROR_MESSAGES: dict[str, str] = {
    "model_service": "The AI service is unavailable right now. Please try again in a moment.",
    "rate_limited": "The AI service is busy. Please wait a few seconds and retry.",
    "retrieval": "I couldn't search the HR documents just now. Please try again.",
    "database": "The HR database is temporarily unavailable.",
    "limit_exceeded": "That request took too many steps. Please try a narrower question.",
    "guardrail_input": "Please send a shorter message (under 4,000 characters).",
    "guardrail_output": "I can't share that information with your role.",
    "configuration": ("The assistant is not configured correctly. Please contact the "
                      "administrator."),
}

try:  # present in openai-agents 0.24 (T007); keep the mapping robust if renamed
    from agents import ModelTimeoutError
except ImportError:  # pragma: no cover
    ModelTimeoutError = TimeoutError  # type: ignore[misc,assignment]


@dataclass(frozen=True)
class ProgressEvent:
    kind: Literal["tool_started", "tool_finished"]
    tool_name: str


@dataclass
class TurnResult:
    final_text: str
    citations: list[Citation] = field(default_factory=list)
    ready_draft: LeaveDraft | None = None
    error_category: str | None = None


def categorize(exc: BaseException) -> str:
    """Map an exception from a run to an error category (contracts/agent-tools.md table)."""
    if isinstance(exc, InputGuardrailTripwireTriggered):
        return "guardrail_input"
    if isinstance(exc, OutputGuardrailTripwireTriggered):
        return "guardrail_output"
    if isinstance(exc, MaxTurnsExceeded):
        return "limit_exceeded"
    if isinstance(exc, openai.RateLimitError):
        return "rate_limited"
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError,
                        openai.NotFoundError, ConfigurationError, UserError)):
        return "configuration"
    if isinstance(exc, RetrievalError):
        return "retrieval"
    if isinstance(exc, DatabaseError):
        return "database"
    if isinstance(exc, (openai.OpenAIError, ModelBehaviorError, ModelTimeoutError,
                        ModelServiceError, TimeoutError)):
        return "model_service"
    if isinstance(exc, HCMError) and exc.category in ERROR_MESSAGES:
        return exc.category
    return "model_service"


def _tool_outputs(items: list[Any]) -> list[tuple[str, Any]]:
    """``(tool_name, parsed_output)`` for every tool output produced this turn."""
    names: dict[str, str] = {}
    outputs: list[tuple[str, Any]] = []
    for item in items:
        kind = getattr(item, "type", None)
        raw = getattr(item, "raw_item", None)
        if kind == "tool_call_item":
            call_id = getattr(raw, "call_id", None)
            if call_id:
                names[call_id] = getattr(raw, "name", "")
        elif kind == "tool_call_output_item":
            call_id = raw.get("call_id") if isinstance(raw, dict) else getattr(raw, "call_id",
                                                                               None)
            output = item.output
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except ValueError:
                    continue
            outputs.append((names.get(call_id, ""), output))
    return outputs


def _collect(items: list[Any]) -> tuple[list[Citation], LeaveDraft | None]:
    citations: dict[tuple[str, str, int | None], Citation] = {}
    draft: LeaveDraft | None = None
    for name, output in _tool_outputs(items):
        if not isinstance(output, dict) or not output.get("ok"):
            continue
        data = output.get("data") or {}
        if name == POLICY_TOOL and data.get("found"):
            for chunk in data.get("chunks", []):
                try:
                    c = Citation.model_validate(chunk["citation"])
                except (KeyError, ValueError, TypeError):
                    continue
                citations.setdefault((c.document_id, c.section, c.page), c)
        elif name == DRAFT_TOOL:
            try:
                candidate = LeaveDraft.model_validate(data)
            except ValueError:
                continue
            draft = candidate if candidate.status == DraftStatus.READY_FOR_REVIEW else None
    return list(citations.values()), draft


async def run_turn(
    ctx: AppContext,
    user_message: str,
    on_progress: Callable[[ProgressEvent], Awaitable[None]] | None = None,
) -> TurnResult:
    services = ctx.services
    history = list(getattr(ctx.session, "history", []))
    turn_input = [*history, {"role": "user", "content": user_message}]
    started = time.monotonic()
    try:
        if services.agent is None:
            raise ConfigurationError("agent not configured")
        result = Runner.run_streamed(services.agent, turn_input, context=ctx,
                                     max_turns=services.max_turns,
                                     run_config=services.run_config)
        async for event in result.stream_events():
            if on_progress is None or getattr(event, "type", None) != "run_item_stream_event":
                continue
            item = event.item
            if event.name == "tool_called":
                await on_progress(ProgressEvent("tool_started",
                                                getattr(item.raw_item, "name", "tool")))
            elif event.name == "tool_output":
                await on_progress(ProgressEvent("tool_finished", "tool"))
        final_text = str(result.final_output or "").strip()
        citations, draft = _collect(result.new_items)
        if hasattr(ctx.session, "history"):
            ctx.session.history = result.to_input_list()
        logger.info("turn.completed", extra={
            "outcome": "ok", "duration_ms": int((time.monotonic() - started) * 1000)})
        return TurnResult(final_text=final_text, citations=citations, ready_draft=draft)
    except Exception as exc:  # map everything; never leak exception text
        category = categorize(exc)
        logger.warning("turn.failed", extra={
            "category": category, "outcome": "error",
            "duration_ms": int((time.monotonic() - started) * 1000)})
        return TurnResult(final_text=ERROR_MESSAGES[category], error_category=category)
