"""Health route (US8 T090, contracts/api.md): no auth, never raises."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    database = "ok"
    try:
        from hcm_lite.db.engine import ping

        if not await ping(request.app.state.engine):
            database = "unavailable"
    except Exception:
        database = "unavailable"
    try:
        vector_index = "ok" if request.app.state.vector_count() >= 0 else "unavailable"
    except Exception:
        vector_index = "unavailable"
    status = "ok" if database == "ok" else "degraded"
    return {"status": status, "database": database, "vector_index": vector_index,
            "demo_mode": True}
