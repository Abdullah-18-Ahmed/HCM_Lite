"""The single HR agent (research D-07)."""

from __future__ import annotations

from typing import Any

from agents import Agent, ModelSettings, RunConfig

from hcm_lite.assistant.context import AppContext
from hcm_lite.assistant.guardrails import build_guardrails
from hcm_lite.assistant.instructions import build_instructions

AGENT_NAME = "HCM Lite HR Assistant"


def build_agent(settings: Any, tools: list, model: Any = None) -> Agent[AppContext]:
    """``model`` is injectable for tests (``ScriptedModel``); default ``OPENAI_MODEL``."""
    input_guardrail, output_guardrail = build_guardrails()
    return Agent[AppContext](
        name=AGENT_NAME,
        instructions=build_instructions,
        tools=list(tools),
        model=model if model is not None else settings.openai_model,
        model_settings=ModelSettings(timeout=settings.model_timeout_seconds),
        input_guardrails=[input_guardrail],
        output_guardrails=[output_guardrail],
    )


def production_run_config() -> RunConfig:
    """Tracing is disabled: no traces leave the machine (research.md, Phase 2 batch C)."""
    return RunConfig(tracing_disabled=True, workflow_name="hcm_lite_turn")
