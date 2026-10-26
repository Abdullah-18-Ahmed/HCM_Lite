"""First-run setup routes: bootstrap the first admin account (no auth)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["setup"])


class AdminSetup(BaseModel):
    email: str
    password: str
    name: str


@router.get("/setup/status")
async def status(request: Request) -> dict:
    svc = request.app.state.services.user_admin
    return {"needs_admin": not await svc.admin_exists()}


@router.post("/setup/admin", status_code=201)
async def create_admin(body: AdminSetup, request: Request):
    svc = request.app.state.services.user_admin
    if await svc.admin_exists():
        return JSONResponse(status_code=409, content={"error": {"code": "already_initialised"}})
    await svc.bootstrap_admin(email=body.email, password=body.password, name=body.name)
    return {"ok": True}
