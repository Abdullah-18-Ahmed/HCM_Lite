"""User administration routes (admin / hr_admin) and self password change.

Thin adapters: validate the body, resolve the acting user from the token, call one
``UserAdminService`` / ``AuthService`` method. Authorization lives in the services; errors are
mapped to status codes by the handlers in ``hcm_lite.api.main``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from hcm_lite.api.deps import current_user, services
from hcm_lite.models.domain import AuthenticatedUser

router = APIRouter(tags=["users"])


class CreateUserBody(BaseModel):
    email: str
    password: str
    name: str
    role: str
    department: str
    job_title: str


class UpdateUserBody(BaseModel):
    name: str | None = None
    department: str | None = None
    job_title: str | None = None
    role: str | None = None


class ActiveBody(BaseModel):
    active: bool


class PasswordBody(BaseModel):
    old_password: str
    new_password: str


@router.get("/users")
async def list_users(user: AuthenticatedUser = Depends(current_user),
                     svc=Depends(services)) -> dict:
    return {"users": await svc.user_admin.list_users(user)}


@router.post("/users", status_code=201)
async def create_user(body: CreateUserBody,
                      user: AuthenticatedUser = Depends(current_user),
                      svc=Depends(services)) -> dict:
    return await svc.user_admin.create_user(
        user, email=body.email, password=body.password, name=body.name, role=body.role,
        department=body.department, job_title=body.job_title)


@router.patch("/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserBody,
                      user: AuthenticatedUser = Depends(current_user),
                      svc=Depends(services)) -> dict:
    return await svc.user_admin.update_user(
        user, user_id, name=body.name, department=body.department, job_title=body.job_title,
        role=body.role)


@router.post("/users/{user_id}/active")
async def set_active(user_id: str, body: ActiveBody,
                     user: AuthenticatedUser = Depends(current_user),
                     svc=Depends(services)) -> dict:
    return await svc.user_admin.set_active(user, user_id, body.active)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, user: AuthenticatedUser = Depends(current_user),
                      svc=Depends(services)) -> None:
    await svc.user_admin.delete_user(user, user_id)


@router.post("/me/password", status_code=204)
async def change_password(body: PasswordBody,
                          user: AuthenticatedUser = Depends(current_user),
                          svc=Depends(services)) -> None:
    await svc.auth.change_password(user, body.old_password, body.new_password)
