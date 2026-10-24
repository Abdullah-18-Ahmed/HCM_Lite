"""T043 local fixtures: a populated app runtime and a mocked Chainlit ``cl`` surface.

``app.py``'s handlers are plain module-level functions (the Chainlit decorators return the
original function), so the tests call them directly with ``cl.user_session``, ``cl.Message``
and ``cl.Step`` replaced by fakes. No Chainlit server is started and no network is used.
"""

from __future__ import annotations

from typing import Any

import pytest

import app as app_module


class FakeUserSession:
    """Dict-backed stand-in for ``cl.user_session`` (one browser session)."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value


@pytest.fixture
def runtime(settings, sf, engine, auditor, authz, auth_service):
    """Populate ``app._runtime`` so the lazy ``startup()`` (network checks) never runs."""
    from tests.conftest import build_test_services

    services = build_test_services(settings, sf, auditor, authz, auth_service)
    app_module._runtime.clear()
    app_module._runtime.update(settings=settings, auth=auth_service, services=services)
    yield app_module._runtime
    app_module._runtime.clear()


def use_scripted_model(runtime: dict[str, Any], steps: list[Any],
                       tools: list[Any] | None = None) -> None:
    """Point the runtime's agent at a ``ScriptedModel`` (offline, deterministic)."""
    from hcm_lite.assistant.hr_agent import build_agent
    from hcm_lite.assistant.tools import TOOLS
    from tests.fakes.scripted_model import ScriptedModel

    runtime["services"].agent = build_agent(runtime["settings"],
                                            TOOLS if tools is None else tools,
                                            model=ScriptedModel(steps))


@pytest.fixture(autouse=True)
def sidebar(monkeypatch) -> list[tuple]:
    """Autouse for the integration package: replaces ``cl.ElementSidebar`` and ``cl.Text``.

    Records ("title", title) and ("elements", els, key). ``cl.Text`` needs a live Chainlit
    session context, so the sidebar element is stubbed with a plain object exposing
    ``name``/``content``/``for_id``.
    """
    calls: list[tuple] = []

    class FakeText:
        def __init__(self, content: Any = None, name: str = "", display: str = "side",
                     for_id: str | None = None, **kwargs: Any) -> None:
            self.content = content
            self.name = name
            self.display = display
            self.for_id = for_id
            self.kwargs = kwargs

    class FakeElementSidebar:
        @staticmethod
        async def set_title(title: str) -> None:
            calls.append(("title", title))

        @staticmethod
        async def set_elements(elements: list, key: str | None = None) -> None:
            calls.append(("elements", list(elements), key))

    monkeypatch.setattr(app_module.cl, "Text", FakeText)
    monkeypatch.setattr(app_module.cl, "ElementSidebar", FakeElementSidebar)
    return calls


@pytest.fixture
def user_session(monkeypatch) -> FakeUserSession:
    fake = FakeUserSession()
    monkeypatch.setattr(app_module.cl, "user_session", fake)
    return fake


@pytest.fixture
def sent(monkeypatch) -> list[Any]:
    """Replace ``cl.Message``; collects every message the app sends."""
    record: list[Any] = []

    class FakeMessage:
        def __init__(self, content: Any = None, **kwargs: Any) -> None:
            self.content = content
            self.kwargs = kwargs

        async def send(self) -> "FakeMessage":
            record.append(self)
            return self

    monkeypatch.setattr(app_module.cl, "Message", FakeMessage)
    return record


@pytest.fixture
def steps(monkeypatch) -> list[Any]:
    """Replace ``cl.Step``; collects every progress step the app creates."""
    record: list[Any] = []

    class FakeStep:
        def __init__(self, name: str | None = None, **kwargs: Any) -> None:
            self.name = name
            self.kwargs = kwargs
            self.removed = False

        async def send(self) -> "FakeStep":
            record.append(self)
            return self

        async def remove(self) -> None:
            self.removed = True

    monkeypatch.setattr(app_module.cl, "Step", FakeStep)
    return record
