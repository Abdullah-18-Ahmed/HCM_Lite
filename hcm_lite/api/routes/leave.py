"""Leave read routes (US8 T091, contracts/api.md)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from hcm_lite.api.deps import current_user, services
from hcm_lite.models.domain import AuthenticatedUser

router = APIRouter(tags=["leave"])


@router.get("/leave/balance")
async def balance(leave_type: str | None = None,
                  user: AuthenticatedUser = Depends(current_user),
                  svc=Depends(services)) -> dict:
    return (await svc.leave.my_balance(user, leave_type)).model_dump(mode="json")


@router.get("/leave/requests")
async def requests(limit: int = Query(10, ge=1, le=50),
                   user: AuthenticatedUser = Depends(current_user),
                   svc=Depends(services)) -> dict:
    return (await svc.leave.my_requests(user, limit)).model_dump(mode="json")
