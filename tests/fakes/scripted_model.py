"""``ScriptedModel(agents.Model)`` for offline agent tests (research D-10, T007).

A script is a list of steps, consumed one per model call:

- ``str`` → a final assistant message;
- ``ToolCall(name, args)`` (or a list of them) → function-tool calls;
- an ``Exception`` instance → raised from the model call.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from agents import Model, ModelResponse
from agents.usage import Usage
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


def _message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id=f"msg_{uuid.uuid4().hex[:8]}", type="message", role="assistant", status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


def _call(call: ToolCall) -> ResponseFunctionToolCall:
    cid = f"call_{uuid.uuid4().hex[:8]}"
    return ResponseFunctionToolCall(id=f"fc_{cid}", call_id=cid, name=call.name,
                                    arguments=json.dumps(call.args), type="function_call",
                                    status="completed")


class ScriptedModel(Model):
    def __init__(self, steps: list[Any]) -> None:
        self.steps = list(steps)
        self.calls: list[dict[str, Any]] = []  # what the model received (instructions, input)

    def _next_output(self, system_instructions: Any, input: Any, tools: Any) -> list[Any]:
        self.calls.append({"instructions": system_instructions, "input": input,
                           "tools": [getattr(t, "name", None) for t in (tools or [])]})
        step = self.steps.pop(0) if self.steps else "(script exhausted)"
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, ToolCall):
            return [_call(step)]
        if isinstance(step, list):
            return [_call(s) for s in step]
        return [_message(str(step))]

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, *args, **kwargs):
        output = self._next_output(system_instructions, input, tools)
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    async def stream_response(self, system_instructions, input, model_settings, tools,
                              output_schema, handoffs, tracing, *args, **kwargs):
        output = self._next_output(system_instructions, input, tools)
        response = Response(id=f"resp_{uuid.uuid4().hex[:8]}", created_at=0, model="scripted",
                            object="response", output=output, parallel_tool_calls=False,
                            tool_choice="auto", tools=[])
        yield ResponseCompletedEvent(type="response.completed", response=response,
                                     sequence_number=0)
