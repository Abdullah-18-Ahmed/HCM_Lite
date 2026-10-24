"""Policy search route (US8 T091, contracts/api.md)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from hcm_lite.api.deps import current_user, services
from hcm_lite.models.domain import AuthenticatedUser
from hcm_lite.models.requests import PolicyQuery

router = APIRouter(tags=["policies"])


@router.post("/policies/search")
async def search(query: PolicyQuery,
                 user: AuthenticatedUser = Depends(current_user),
                 svc=Depends(services)) -> dict:
    return (await svc.policy.search(user, query.query, query.doc_type)).model_dump(mode="json")
