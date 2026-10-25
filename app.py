"""Chainlit wiring for HCM Lite (contracts/ui.md, tasks T042).

Composition root only: every decision lives in ``hcm_lite/services`` or the assistant runner.
This module imports no sqlalchemy and no repository and runs no SQL — the data path is
``app.py → hcm_lite.services → repositories``. Startup fails fast and clearly on missing
configuration, a database that is not at the latest migration, or an unavailable model.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import chainlit as cl
from chainlit.auth import decode_jwt, get_token_from_cookies

from hcm_lite.assistant.context import AppContext, AppSession, Services
from hcm_lite.assistant.hr_agent import build_agent, production_run_config
from hcm_lite.assistant.runner import ProgressEvent, run_turn
from hcm_lite.assistant.tools import TOOLS
from hcm_lite.config import get_settings, verify_models
from hcm_lite.db.engine import assert_at_head, create_engine, session_factory
from hcm_lite.models.domain import AuthenticatedUser, Role
from hcm_lite.rag.embeddings import OpenAIEmbedder
from hcm_lite.rag.retriever import Retriever
from hcm_lite.rag.vector_store import QdrantStore
from hcm_lite.services.audit import Auditor, new_correlation_id
from hcm_lite.services.auth_service import AuthService
from hcm_lite.services.authz import Authz
from hcm_lite.services.dashboard_service import DashboardService
from hcm_lite.services.leave_service import LeaveService
from hcm_lite.services.metrics_service import MetricsService
from hcm_lite.services.policy_service import PolicyService
from hcm_lite.ui.render import render_dashboard, render_draft, render_error, render_sources

logger = logging.getLogger("hcm_lite.app")

SESSION_KEY = "app_session"
USER_KEY = "user"  # where Chainlit stores the authenticated ``cl.User``

SIDEBAR_TITLE = "Dashboard"
SIDEBAR_KEY = "dashboard"
DASHBOARD_ERROR = "The dashboard could not be loaded. Please try refreshing."

WELCOME = (
    "Welcome to HCM Lite. You are signed in as **{role}**.\n\n"
    "Ask me about HR policies, leave balances or your figures.\n\n"
    "Demo data — all records in this environment are fictional."
)
SESSION_EXPIRED = (
    "Your session expired after {minutes} minutes of inactivity. Please sign in again."
)
SIGNED_OUT = "This account is no longer active. Please sign in again."

# Starters per role (contracts/ui.md): managers and HR admins get the employee set plus
# role-specific entries.
EMPLOYEE_STARTERS: tuple[tuple[str, str], ...] = (
    ("Annual leave policy", "What is the annual leave policy?"),
    ("My leave balance", "What is my leave balance?"),
    ("Prepare a leave request", "Prepare a leave request for next Monday and Tuesday."),
    ("Summarize my dashboard", "Summarize my dashboard."),
)
STARTERS: dict[Role, tuple[tuple[str, str], ...]] = {
    Role.EMPLOYEE: EMPLOYEE_STARTERS,
    Role.MANAGER: EMPLOYEE_STARTERS + (
        ("Team attendance this month", "Summarize my team's attendance this month."),
        ("Who was late today?", "Who was late today?"),
    ),
    Role.HR_ADMIN: EMPLOYEE_STARTERS + (
        ("How many employees?", "How many employees are there in total?"),
        ("Payroll last month", "What was the total payroll last month?"),
    ),
}

_runtime: dict[str, Any] = {}


# --------------------------------------------------------------------------- startup


async def startup() -> dict[str, Any]:
    """Build the engine, services and agent once; fail fast on any startup problem."""
    if _runtime:
        return _runtime
    settings = get_settings()  # ConfigurationError naming the missing variables
    engine = create_engine(settings)
    await assert_at_head(engine)  # ConfigurationError: schema out of date
    await verify_models(settings)  # ConfigurationError/ModelServiceError: model unavailable
    factory = session_factory(engine)
    auditor = Auditor(factory)
    auth = AuthService.from_settings(settings, factory, auditor)
    authz = Authz(factory, auditor)
    embedder = OpenAIEmbedder(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_embedding_model, timeout=settings.model_timeout_seconds)
    retriever = Retriever(lambda: QdrantStore.from_settings(settings), embedder, settings)
    policy = PolicyService(retriever)
    metrics = MetricsService(factory, authz, late_grace_minutes=settings.late_grace_minutes)
    leave = LeaveService(factory, authz, auditor, policy=policy)
    services = Services(auth=auth, metrics=metrics, leave=leave, policy=policy,
                        dashboard=DashboardService(metrics, leave),
                        run_config=production_run_config(),
                        max_turns=settings.agent_max_turns)
    services.agent = build_agent(settings, TOOLS)
    index_empty = retriever.count() == 0
    _runtime.update(settings=settings, engine=engine, auth=auth, services=services,
                    index_empty=index_empty)
    logger.info("app.started", extra={"outcome": "ok"})
    return _runtime


async def get_runtime() -> dict[str, Any]:
    """The process-wide runtime, built lazily so tests can inject their own."""
    return _runtime if _runtime else await startup()


@cl.on_app_startup
async def on_app_startup() -> None:
    await startup()


# --------------------------------------------------------------------------- sign-in


@cl.password_auth_callback
async def password_auth_callback(username: str, password: str) -> cl.User | None:
    """The only chat sign-in path; the role never enters the ``cl.User`` metadata."""
    runtime = await get_runtime()
    user = await runtime["auth"].authenticate(username, password, channel="chat")
    if user is None:
        return None
    return cl.User(identifier=user.user_id,
                   metadata={"username": user.username, "display_name": user.display_name})


@cl.set_starters
async def starters(current_user: cl.User | None = None,
                   language: str | None = None) -> list[cl.Starter]:
    """Role-specific starters; the role is reloaded from the database every time."""
    if current_user is None:
        return []
    runtime = await get_runtime()
    user = await runtime["auth"].load_user(current_user.identifier)
    if user is None:
        return []
    return [cl.Starter(label=label, message=message)
            for label, message in STARTERS.get(user.role, EMPLOYEE_STARTERS)]


# --------------------------------------------------------------------------- chat


async def _session_user(runtime: dict[str, Any]) -> AuthenticatedUser | None:
    """Idle + user checks shared by ``on_message`` and the refresh action.

    On failure this sends the expiry / sign-in message, audits ``session_expired`` where
    applicable and ends the session, then returns None. On success it reloads the user from
    the database, refreshes the session's copy and touches the idle timer.
    """
    cl_user = cl.user_session.get(USER_KEY)
    if cl_user is None:
        return None
    session = cl.user_session.get(SESSION_KEY)
    if session is None:  # already expired or signed out earlier in this chat
        await cl.Message(_expired_text(runtime)).send()
        return None
    if session.is_idle():
        await runtime["services"].auth.record_logout(session.user, "session_expired")
        cl.user_session.set(SESSION_KEY, None)  # end the session
        await cl.Message(_expired_text(runtime)).send()
        return None
    user = await runtime["services"].auth.load_user(cl_user.identifier)
    if user is None:
        await cl.Message(SIGNED_OUT).send()
        return None
    session.user = user  # fresh identity and role for this turn
    session.touch()
    return user


async def _render_sidebar(runtime: dict[str, Any], user: AuthenticatedUser) -> None:
    """Render the role dashboard into the element sidebar (T054, contracts/ui.md)."""
    try:
        data = await runtime["services"].dashboard.for_user(user, _today(runtime))
        markdown = render_dashboard(data)
    except Exception:  # a broken dashboard never breaks the chat
        markdown = render_error(DASHBOARD_ERROR)
    await cl.ElementSidebar.set_title(SIDEBAR_TITLE)
    await cl.ElementSidebar.set_elements(
        [cl.Text(name=SIDEBAR_TITLE, content=markdown)], key=SIDEBAR_KEY)


def _refresh_action() -> cl.Action:
    return cl.Action(name="refresh_dashboard", payload={}, label="Refresh dashboard")


def _today(runtime: dict[str, Any]):
    return datetime.now(runtime["settings"].tz).date()


@cl.on_chat_start
async def on_chat_start() -> None:
    runtime = await get_runtime()
    cl_user = cl.user_session.get(USER_KEY)
    if cl_user is None:
        return
    user = await runtime["auth"].load_user(cl_user.identifier)
    if user is None:  # deleted or deactivated since sign-in
        await cl.Message(SIGNED_OUT).send()
        return
    cl.user_session.set(SESSION_KEY, AppSession(
        user=user, idle_minutes=runtime["settings"].session_idle_minutes))
    await _render_sidebar(runtime, user)
    welcome = WELCOME.format(role=user.role.value)
    if runtime.get("index_empty"):
        welcome += ("\n\n> Note: the HR document index is empty — run "
                    "`python -m hcm_lite.rag.ingest ingest` before asking policy questions.")
    await cl.Message(welcome, actions=[_refresh_action()]).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    runtime = await get_runtime()
    new_correlation_id()  # one correlation id per turn (logs and audit rows)
    user = await _session_user(runtime)
    if user is None:
        return
    session = cl.user_session.get(SESSION_KEY)
    await _answer(runtime, session, message)


async def _answer(runtime: dict[str, Any], session: AppSession, message: cl.Message) -> None:
    """Run one assistant turn, showing tool progress as transient ``cl.Step``s."""
    services: Services = runtime["services"]
    ctx = AppContext(user=session.user, session=session, today=_today(runtime),
                     services=services)
    open_steps: list[cl.Step] = []

    async def on_progress(event: ProgressEvent) -> None:
        if event.kind == "tool_started":
            step = cl.Step(name=event.tool_name, type="tool")
            await step.send()
            open_steps.append(step)
        elif open_steps:  # "tool_finished": the runner reports the generic name
            await open_steps.pop().remove()

    result = await run_turn(ctx, message.content, on_progress=on_progress)
    for step in open_steps:  # close anything left open by an error path
        await step.remove()

    content = result.final_text
    if result.citations:
        sources = render_sources(result.citations)
        content = f"{content}\n\n{sources}" if content else sources
    actions: list[cl.Action] = []
    if result.ready_draft is not None:
        draft_md = render_draft(result.ready_draft)
        content = f"{content}\n\n{draft_md}" if content else draft_md
        actions = [
            cl.Action(name="confirm_leave", payload={"draft_id": result.ready_draft.draft_id},
                      label="Confirm"),
            cl.Action(name="cancel_leave", payload={"draft_id": result.ready_draft.draft_id},
                      label="Cancel"),
        ]
    await cl.Message(content=content, actions=actions).send()


def _expired_text(runtime: dict[str, Any]) -> str:
    return SESSION_EXPIRED.format(minutes=runtime["settings"].session_idle_minutes)


# --------------------------------------------------------------------------- dashboard action


@cl.action_callback("refresh_dashboard")
async def refresh_dashboard(action: cl.Action) -> None:
    """Re-check idle and the user, then re-render the sidebar; never raises into Chainlit."""
    try:
        runtime = await get_runtime()
        new_correlation_id()
        user = await _session_user(runtime)
        if user is not None:
            await _render_sidebar(runtime, user)
    except Exception:  # noqa: BLE001 — a failed refresh must never break the action
        logger.warning("app.refresh_failed", extra={"outcome": "error"})


# --------------------------------------------------------------------------- leave actions (US5)


SUBMITTED = ("Submitted. Your leave request **{reference}** is now pending approval.\n\n"
             "Demo data — this request is stored in the demonstration database.")
DRAFT_GONE = "This draft is no longer available. Ask me to prepare the request again."
CANCELLED = "Draft cancelled. Nothing was submitted."

SYSTEM_NOTE = "Leave request submitted with reference {reference} (status pending)."


async def _leave_actions(runtime: dict[str, Any], action: cl.Action, *, confirm: bool) -> None:
    """Shared confirm/cancel path: idle + user checks, then submit or discard."""
    try:
        new_correlation_id()
        user = await _session_user(runtime)
        if user is None:
            return
        session = cl.user_session.get(SESSION_KEY)
        if session is None:
            return
        draft_id = str((action.payload or {}).get("draft_id", ""))
        if confirm:
            try:
                record = await runtime["services"].leave.submit(
                    user, session, draft_id, channel="chat", today=_today(runtime))
            except Exception:
                await cl.Message(DRAFT_GONE).send()
                return
            session.history.append(
                {"role": "system", "content": SYSTEM_NOTE.format(reference=record.id)})
            await cl.Message(SUBMITTED.format(reference=record.id)).send()
        else:
            session.discard_draft(draft_id)
            await cl.Message(CANCELLED).send()
    except Exception:  # noqa: BLE001 — a failed action must never break the chat
        logger.warning("app.leave_action_failed", extra={"outcome": "error"})


@cl.action_callback("confirm_leave")
async def confirm_leave(action: cl.Action) -> None:
    await _leave_actions(await get_runtime(), action, confirm=True)


@cl.action_callback("cancel_leave")
async def cancel_leave(action: cl.Action) -> None:
    await _leave_actions(await get_runtime(), action, confirm=False)


# --------------------------------------------------------------------------- logout


@cl.on_logout
async def on_logout(request: Any, response: Any) -> None:
    """Best-effort logout audit: decode the auth cookie; never raise into the response."""
    try:
        token = get_token_from_cookies(request.cookies)
        if not token:
            return
        cl_user = decode_jwt(token)
        if cl_user is None:
            return
        runtime = await get_runtime()
        await runtime["auth"].record_logout(cl_user.identifier, "logout")
    except Exception:  # noqa: BLE001 — a failed audit must never break the logout
        logger.info("app.logout_audit_skipped", extra={"outcome": "skipped"})
