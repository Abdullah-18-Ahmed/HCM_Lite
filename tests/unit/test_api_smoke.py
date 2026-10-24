"""T007 API smoke test: resolves every VERIFY-AT-IMPL item in research.md.

Findings are recorded in specs/002-hcm-lite-ai-app/research.md under
"Verification results (T007)". Offline only: temporary SQLite files, no OpenAI calls.
"""

from __future__ import annotations

import inspect
import tomllib
import types
from pathlib import Path

import pytest

# Module-level import is required: with `from __future__ import annotations` the SDK resolves
# tool parameter annotations through the defining module's globals (finding in research.md).
from agents import RunContextWrapper

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- Agents SDK (D-07)


def test_agents_core_exports():
    from agents import (  # noqa: F401
        Agent,
        GuardrailFunctionOutput,
        MaxTurnsExceeded,
        ModelSettings,
        RunContextWrapper,
        Runner,
        input_guardrail,
        output_guardrail,
    )
    # Error types the runner maps (contracts/agent-tools.md).
    from agents import (  # noqa: F401
        InputGuardrailTripwireTriggered,
        ModelBehaviorError,
        ModelTimeoutError,
        OutputGuardrailTripwireTriggered,
        ToolTimeoutError,
        UserError,
    )


def test_tool_decorator_is_agents_function_tool():
    """Finding: use `agents.function_tool`. `agents.decorators.tool` is the same object;
    top-level `agents.tool` is a *module*, not a decorator."""
    import agents
    import agents.decorators

    assert callable(agents.function_tool)
    assert agents.decorators.tool is agents.function_tool
    assert isinstance(agents.tool, types.ModuleType)

    params = inspect.signature(agents.function_tool).parameters
    for name in ("timeout", "timeout_behavior", "failure_error_function", "strict_mode"):
        assert name in params, name
    assert params["timeout_behavior"].default == "error_as_result"


def test_function_tool_exposes_params_json_schema():
    from agents import FunctionTool, function_tool

    @function_tool(timeout=10, timeout_behavior="error_as_result")
    async def probe(ctx: RunContextWrapper[object], period: str) -> str:
        """Probe tool.

        Args:
            period: A period keyword.
        """
        return period

    assert isinstance(probe, FunctionTool)
    props = probe.params_json_schema["properties"]
    assert set(props) == {"period"}  # the context parameter is not exposed to the model


def test_model_settings_has_timeout():
    import dataclasses

    from agents import ModelSettings

    assert "timeout" in {f.name for f in dataclasses.fields(ModelSettings)}


def test_runner_run_streamed_signature():
    from agents import RunResultStreaming, Runner

    params = inspect.signature(Runner.run_streamed).parameters
    assert {"starting_agent", "input", "context", "max_turns", "run_config"} <= set(params)
    assert hasattr(RunResultStreaming, "to_input_list")


# Scripted model (D-10): a `Model` subclass is accepted by Agent(model=...) for both
# Runner.run and Runner.run_streamed, so no patching of Runner.run_streamed is needed.


def _scripted_model(text: str):
    from agents import Model, ModelResponse
    from agents.usage import Usage
    from openai.types.responses import (
        Response,
        ResponseCompletedEvent,
        ResponseOutputMessage,
        ResponseOutputText,
    )

    def message():
        return ResponseOutputMessage(
            id="msg_1",
            type="message",
            role="assistant",
            status="completed",
            content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
        )

    class ScriptedModel(Model):
        async def get_response(self, *args, **kwargs):
            return ModelResponse(output=[message()], usage=Usage(), response_id=None)

        async def stream_response(self, *args, **kwargs):
            response = Response(
                id="resp_1",
                created_at=0,
                model="scripted",
                object="response",
                output=[message()],
                parallel_tool_calls=False,
                tool_choice="auto",
                tools=[],
            )
            yield ResponseCompletedEvent(
                type="response.completed", response=response, sequence_number=0
            )

    return ScriptedModel()


def test_model_interface_abstract_methods():
    from agents import Model

    assert Model.__abstractmethods__ == frozenset({"get_response", "stream_response"})


async def test_scripted_model_with_runner_run():
    from agents import Agent, RunConfig, Runner

    agent = Agent(name="probe", instructions="x", model=_scripted_model("hello"))
    result = await Runner.run(agent, "hi", run_config=RunConfig(tracing_disabled=True))
    assert result.final_output == "hello"


async def test_scripted_model_with_runner_run_streamed():
    from agents import Agent, RunConfig, Runner

    agent = Agent(name="probe", instructions="x", model=_scripted_model("streamed"))
    result = Runner.run_streamed(
        agent, "hi", max_turns=3, run_config=RunConfig(tracing_disabled=True)
    )
    async for _ in result.stream_events():
        pass
    assert result.final_output == "streamed"
    assert len(result.to_input_list()) == 2  # user input + assistant message


# --------------------------------------------------------------------------- SQLite / SQLAlchemy


def test_pymongo_not_installed():
    """MongoDB was dropped (constitution v4.0.0); nothing may depend on pymongo."""
    import importlib.util

    assert importlib.util.find_spec("pymongo") is None


async def test_async_sqlite_engine_pragmas_and_session(tmp_path):
    """create_async_engine + aiosqlite: PRAGMAs set in a sync 'connect' listener on
    engine.sync_engine apply to every pooled connection."""
    import aiosqlite  # noqa: F401
    from sqlalchemy import event, text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'probe.db').as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    try:
        async with engine.connect() as conn:
            assert (await conn.execute(text("SELECT 1"))).scalar() == 1
            assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1
            assert (await conn.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
            assert (await conn.execute(text("PRAGMA busy_timeout"))).scalar() == 5000

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            assert isinstance(session, AsyncSession)
            assert (await session.execute(text("SELECT 1"))).scalar() == 1
    finally:
        await engine.dispose()


def test_alembic_command_and_config_api():
    from pathlib import Path as _Path

    import alembic
    from alembic import command
    from alembic.config import Config

    for name in ("upgrade", "downgrade", "current", "revision", "check"):
        assert callable(getattr(command, name)), name

    cfg = Config()  # programmatic config; no URL needs to live in alembic.ini
    cfg.set_main_option("script_location", "hcm_lite/db/migrations")
    assert cfg.get_main_option("script_location") == "hcm_lite/db/migrations"

    templates = {p.name for p in (_Path(alembic.__file__).parent / "templates").iterdir()}
    assert "async" in templates  # async env.py template exists


# --------------------------------------------------------------------------- FastAPI / JWT


def test_fastapi_depends_with_testclient():
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient  # requires httpx

    app = FastAPI()

    async def answer() -> int:
        return 42

    @app.get("/probe")
    async def probe(value: int = Depends(answer)):
        return {"value": value}

    with TestClient(app) as client:
        response = client.get("/probe")
    assert response.status_code == 200
    assert response.json() == {"value": 42}


def test_jwt_hs256_roundtrip_and_errors():
    import datetime as dt

    import jwt

    secret = "s" * 48
    token = jwt.encode({"sub": "user-1"}, secret, algorithm="HS256")
    assert isinstance(token, str)
    assert jwt.decode(token, secret, algorithms=["HS256"]) == {"sub": "user-1"}

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "t" * 48, algorithms=["HS256"])

    expired = jwt.encode(
        {"sub": "user-1", "exp": dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)},
        secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(expired, secret, algorithms=["HS256"])
    assert issubclass(jwt.ExpiredSignatureError, jwt.InvalidTokenError)


# --------------------------------------------------------------------------- Chainlit (D-01, D-05, D-08)


def test_chainlit_exports_present():
    import chainlit as cl

    for name in (
        "Action",
        "action_callback",
        "ElementSidebar",
        "on_logout",
        "on_chat_end",
        "set_starters",
        "Starter",
        "password_auth_callback",
        "on_chat_start",
        "on_message",
        "Step",
        "User",
        "user_session",
    ):
        assert hasattr(cl, name), name


def test_chainlit_action_and_sidebar_signatures():
    import chainlit as cl

    action_params = inspect.signature(cl.Action).parameters
    assert list(action_params)[:3] == ["name", "payload", "label"]
    assert list(inspect.signature(cl.action_callback).parameters) == ["name"]
    assert list(inspect.signature(cl.ElementSidebar.set_elements).parameters)[:1] == ["elements"]
    assert list(inspect.signature(cl.ElementSidebar.set_title).parameters) == ["title"]


async def test_chainlit_set_starters_receives_current_user():
    """Chainlit calls set_starters(current_user, language); wrap_user_function binds
    positional args to the user function's parameter names, so `current_user` works."""
    import chainlit.server
    from chainlit.utils import wrap_user_function

    assert "config.code.set_starters(current_user" in inspect.getsource(chainlit.server)

    async def starters(current_user):
        return current_user

    sentinel = object()
    assert await wrap_user_function(starters)(sentinel, "en-US") is sentinel


def test_chainlit_on_logout_gets_request_response_and_user_is_recoverable():
    """Finding: on_logout(request, response) receives no user. The user can be recovered
    from the auth cookie with chainlit.auth.get_token_from_cookies + decode_jwt."""
    import chainlit as cl
    from chainlit.auth import decode_jwt, get_token_from_cookies  # noqa: F401

    func_annotation = inspect.signature(cl.on_logout).parameters["func"].annotation
    assert "Request" in str(func_annotation) and "Response" in str(func_annotation)


def test_chainlit_session_timeout_config_key():
    from chainlit.config import ProjectSettings

    fields = ProjectSettings.model_fields
    assert "user_session_timeout" in fields  # JWT expiry + auth cookie max_age (seconds)
    assert "session_timeout" in fields  # websocket reconnect window (seconds)


def test_project_chainlit_config_values():
    config = tomllib.loads((REPO_ROOT / ".chainlit" / "config.toml").read_text("utf-8"))
    assert config["UI"]["name"] == "HCM Lite"
    assert config["project"]["user_session_timeout"] == 60 * 60  # SESSION_IDLE_MINUTES default
    # Least privilege / safe UI defaults (Art. XVI)
    assert config["features"]["spontaneous_file_upload"]["enabled"] is False
    assert config["features"]["unsafe_allow_html"] is False
    assert config["features"]["edit_message"] is False
    assert "*" not in config["project"]["allow_origins"]
    assert config["UI"]["cot"] == "tool_call"


# --------------------------------------------------------------------------- Qdrant (D-09)


@pytest.fixture
def qdrant_memory():
    from qdrant_client import QdrantClient, models

    client = QdrantClient(":memory:")
    client.create_collection(
        "probe", vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE)
    )
    points = [
        ([1.0, 0.0, 0.0], "all_employees", "doc-a"),
        ([1.0, 0.1, 0.0], "managers", "doc-b"),
        ([1.0, 0.2, 0.0], "hr_admin", "doc-c"),
        ([0.9, 0.0, 0.1], "restricted", "doc-d"),
    ]
    client.upsert(
        "probe",
        points=[
            models.PointStruct(
                id=i, vector=v, payload={"access_scope": scope, "document_id": doc}
            )
            for i, (v, scope, doc) in enumerate(points)
        ],
    )
    yield client, models
    client.close()


def test_qdrant_search_api_is_query_points():
    """Finding: QdrantClient.search was removed in 1.20; use query_points."""
    from qdrant_client import QdrantClient

    assert hasattr(QdrantClient, "query_points")


def test_qdrant_memory_match_any_filter(qdrant_memory):
    client, models = qdrant_memory
    scope_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="access_scope", match=models.MatchAny(any=["all_employees", "managers"])
            )
        ]
    )
    hits = client.query_points(
        "probe", query=[1.0, 0.0, 0.0], query_filter=scope_filter, limit=10
    ).points
    assert {h.payload["access_scope"] for h in hits} == {"all_employees", "managers"}

    unfiltered = client.query_points("probe", query=[1.0, 0.0, 0.0], limit=10).points
    assert len(unfiltered) == 4


def test_qdrant_memory_delete_by_payload_filter(qdrant_memory):
    client, models = qdrant_memory
    client.delete(
        "probe",
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value="doc-b")
                    )
                ]
            )
        ),
    )
    assert client.count("probe").count == 3
    assert client.get_collection("probe").config.params.vectors.size == 3
