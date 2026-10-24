"""T018: runner error mapping (contracts/agent-tools.md table); no exception text leaks."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest
from agents import (
    InputGuardrailTripwireTriggered,
    RunContextWrapper,
    MaxTurnsExceeded,
    ModelBehaviorError,
    OutputGuardrailTripwireTriggered,
)

from hcm_lite.assistant.tools import hr_tool
from hcm_lite.assistant.runner import ERROR_MESSAGES, categorize, run_turn
from hcm_lite.errors import ConfigurationError, DatabaseError, RetrievalError
from tests.conftest import ScriptedModel, ToolCall

SECRET = "Jane-Doe-salary-9000"
_REQ = httpx.Request("POST", "https://api.openai.com/v1/responses")


def _status(cls, code):
    return cls(SECRET, response=httpx.Response(code, request=_REQ), body=None)


def _guardrail(cls):
    gr = SimpleNamespace(guardrail=SimpleNamespace(get_name=lambda: "g", name="g"),
                         output=SimpleNamespace(tripwire_triggered=True, output_info=None))
    return cls(gr)


CASES = [
    (lambda: openai.APIConnectionError(message=SECRET, request=_REQ), "model_service"),
    (lambda: openai.APITimeoutError(request=_REQ), "model_service"),
    (lambda: _status(openai.InternalServerError, 500), "model_service"),
    (lambda: ModelBehaviorError(SECRET), "model_service"),
    (lambda: _status(openai.RateLimitError, 429), "rate_limited"),
    (lambda: _status(openai.AuthenticationError, 401), "configuration"),
    (lambda: ConfigurationError(SECRET), "configuration"),
    (lambda: RetrievalError(SECRET), "retrieval"),
    (lambda: DatabaseError(SECRET), "database"),
    (lambda: MaxTurnsExceeded(SECRET), "limit_exceeded"),
    (lambda: _guardrail(InputGuardrailTripwireTriggered), "guardrail_input"),
    (lambda: _guardrail(OutputGuardrailTripwireTriggered), "guardrail_output"),
    (lambda: RuntimeError(SECRET), "model_service"),
]


def test_every_category_has_a_fixed_message():
    assert set(ERROR_MESSAGES) == {
        "model_service", "rate_limited", "retrieval", "database", "limit_exceeded",
        "guardrail_input", "guardrail_output", "configuration"}


@pytest.mark.parametrize(("make", "category"), CASES)
def test_categorize(make, category):
    assert categorize(make()) == category


@pytest.mark.parametrize(("make", "category"), CASES)
async def test_run_turn_maps_errors_without_leaking(make, category, make_ctx):
    ctx = make_ctx(model=ScriptedModel([make()]), tools=[])
    result = await run_turn(ctx, "hello")
    assert result.error_category == category
    assert result.final_text == ERROR_MESSAGES[category]
    assert SECRET not in result.final_text
    assert ctx.session.history == []  # a failed turn is not appended


async def test_max_turns_exceeded_from_a_looping_model(make_ctx):
    @hr_tool
    async def ping(ctx: RunContextWrapper) -> str:
        """Ping."""
        return "{}"

    ctx = make_ctx(model=ScriptedModel([ToolCall("ping")] * 20), tools=[ping])
    result = await run_turn(ctx, "loop")
    assert result.error_category == "limit_exceeded"


async def test_success_updates_history_and_reports_progress(make_ctx):
    @hr_tool
    async def ping(ctx: RunContextWrapper) -> str:
        """Ping."""
        return '{"ok": true, "data": {}}'

    events = []

    async def progress(ev):
        events.append(ev)

    ctx = make_ctx(model=ScriptedModel([ToolCall("ping"), "pong"]), tools=[ping])
    result = await run_turn(ctx, "hi", progress)
    assert result.error_category is None and result.final_text == "pong"
    assert [e.kind for e in events] == ["tool_started", "tool_finished"]
    assert events[0].tool_name == "ping"
    assert len(ctx.session.history) >= 4  # user, call, output, assistant
    second = await run_turn(ctx, "again")
    assert second.error_category is None  # script exhausted → a plain message


async def test_failing_tool_returns_sanitized_result(make_ctx):
    @hr_tool
    async def boom(ctx: RunContextWrapper) -> str:
        """Boom."""
        raise RuntimeError(SECRET)

    model = ScriptedModel([ToolCall("boom"), "done"])
    ctx = make_ctx(model=model, tools=[boom])
    result = await run_turn(ctx, "x")
    assert result.final_text == "done"
    tool_output = str(model.calls[-1]["input"])
    assert "source_unavailable" in tool_output and SECRET not in tool_output
