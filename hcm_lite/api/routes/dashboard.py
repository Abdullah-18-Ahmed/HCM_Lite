"""Dashboard route (US8 T091, contracts/api.md): one service call."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from hcm_lite.api.deps import services, today
from hcm_lite.models.domain import AuthenticatedUser
from hcm_lite.api.deps import current_user

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
async def dashboard(user: AuthenticatedUser = Depends(current_user),
                    svc=Depends(services), _today=Depends(today)) -> dict:
    data = await svc.dashboard.for_user(user, _today)
    return data.model_dump(mode="json")
