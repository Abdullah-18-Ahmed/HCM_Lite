"""FastAPI application (US8, contracts/api.md).

Thin adapters over the shared services: routes validate with Pydantic, resolve the user from
the token, call one service method, and return its result. No route imports sqlalchemy or
repositories; authorization happens in the services (constitution Art. IX.1.4, XIV).
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hcm_lite.api.conversations import ConversationStore
from hcm_lite.api.routes import assistant, auth, dashboard, health, leave, metrics, policies
from hcm_lite.assistant.context import Services
from hcm_lite.assistant.hr_agent import build_agent, production_run_config
from hcm_lite.assistant.tools import TOOLS
from hcm_lite.config import get_settings, verify_models
from hcm_lite.db.engine import assert_at_head, create_engine, dispose, session_factory
from hcm_lite.errors import (
    AccessDenied,
    DatabaseError,
    HCMError,
    NotFound,
    RetrievalError,
    ValidationError,
)
from hcm_lite.rag.embeddings import OpenAIEmbedder
from hcm_lite.rag.retriever import Retriever
from hcm_lite.rag.vector_store import QdrantStore
from hcm_lite.services.audit import Auditor
from hcm_lite.services.auth_service import AuthService
from hcm_lite.services.authz import Authz
from hcm_lite.services.dashboard_service import DashboardService
from hcm_lite.services.leave_service import LeaveService
from hcm_lite.services.metrics_service import MetricsService
from hcm_lite.services.policy_service import PolicyService

logger = logging.getLogger("hcm_lite.api")


def _error(code: str, message: str | None = None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code}
    if message is not None:
        body["message"] = message
    body.update(extra)
    return {"error": body}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()  # ConfigurationError naming the variables
    engine = create_engine(settings)
    await assert_at_head(engine)
    await verify_models(settings)
    factory = session_factory(engine)
    auditor = Auditor(factory)
    auth = AuthService.from_settings(settings, factory, auditor)
    authz = Authz(factory, auditor)
    embedder = OpenAIEmbedder(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_embedding_model, timeout=settings.model_timeout_seconds)
    retriever = Retriever(QdrantStore.from_settings(settings), embedder, settings)
    policy = PolicyService(retriever)
    metrics_svc = MetricsService(factory, authz, late_grace_minutes=settings.late_grace_minutes)
    leave_svc = LeaveService(factory, authz, auditor, policy=policy)
    services = Services(auth=auth, metrics=metrics_svc, leave=leave_svc, policy=policy,
                        dashboard=DashboardService(metrics_svc, leave_svc),
                        run_config=production_run_config(),
                        max_turns=settings.agent_max_turns)
    services.agent = build_agent(settings, TOOLS)
    app.state.settings = settings
    app.state.engine = engine
    app.state.services = services
    app.state.conversations = ConversationStore(idle_minutes=settings.session_idle_minutes)
    app.state.vector_count = lambda: retriever._store.count()  # noqa: SLF001
    logger.info("api.started", extra={"outcome": "ok"})
    try:
        yield
    finally:
        await dispose(engine)
        logger.info("api.stopped", extra={"outcome": "ok"})


app = FastAPI(title="HCM Lite API", version="1.0.0", lifespan=lifespan)

if True:  # keep handlers/middleware grouped below the app object
    @app.middleware("http")
    async def correlation_id(request: Request, call_next: Any) -> Any:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    @app.exception_handler(AccessDenied)
    async def _access_denied(_request: Request, exc: AccessDenied) -> JSONResponse:
        return JSONResponse(status_code=403, content=_error("access_denied", str(exc.capability)))

    @app.exception_handler(ValidationError)
    async def _invalid_input(_request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422,
                            content=_error("invalid_input", exc.message, field=exc.field))

    @app.exception_handler(RequestValidationError)
    async def _pydantic_invalid(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({str(e["loc"][0]) for e in exc.errors() if e.get("loc")})
        return JSONResponse(
            status_code=422,
            content=_error("invalid_input", "invalid value for: " + ", ".join(fields)))

    @app.exception_handler(NotFound)
    async def _not_found(_request: Request, _exc: NotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content=_error("not_found"))

    @app.exception_handler(DatabaseError)
    async def _database(_request: Request, _exc: DatabaseError) -> JSONResponse:
        return JSONResponse(status_code=503, content=_error("database_unavailable"))

    @app.exception_handler(RetrievalError)
    async def _retrieval(_request: Request, exc: RetrievalError) -> JSONResponse:
        return JSONResponse(status_code=503, content=_error(exc.category or "source_unavailable"))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_error("internal_error",
                           correlation_id=getattr(request.state, "correlation_id", None)))

    try:  # CORS config is optional; the lifespan re-validates settings and fails fast
        cors_origins = get_settings().cors_origins
    except Exception:
        cors_origins = []
    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=cors_origins,
                           allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(leave.router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(assistant.router, prefix="/api/v1")
