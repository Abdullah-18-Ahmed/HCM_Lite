"""Auth routes (US8 T090, contracts/api.md)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm

from hcm_lite.api.deps import current_user
from hcm_lite.models.domain import AuthenticatedUser

router = APIRouter(tags=["auth"])

INVALID_CREDENTIALS = {"error": {"code": "invalid_credentials",
                                 "message": "Invalid username or password."}}


@router.post("/auth/token")
async def token(request: Request, form: OAuth2PasswordRequestForm = Depends()) -> dict:
    auth = request.app.state.services.auth
    user = await auth.authenticate(form.username, form.password, channel="api")
    if user is None:  # wrong password, unknown user, locked or inactive: the same 401
        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)
    jwt_token, expires_in = auth.issue_token(user)
    return {"access_token": jwt_token, "token_type": "bearer", "expires_in": expires_in}


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, user: AuthenticatedUser = Depends(current_user)) -> None:
    bearer = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    await request.app.state.services.auth.revoke_token(bearer)
    await request.app.state.services.auth.record_logout(user, "logout")
