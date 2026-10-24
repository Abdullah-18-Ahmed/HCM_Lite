"""Shared FastAPI dependencies (US8, contracts/api.md).

``current_user`` verifies the bearer token and reloads the user from the database; any
failure produces the same generic 401 body — the reason ("expired"/"revoked") never leaves
the server.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from hcm_lite.errors import InvalidToken
from hcm_lite.models.domain import AuthenticatedUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def _unauthorized() -> HTTPException:
    # L5: always the same generic body; never the InvalidToken reason.
    return HTTPException(status_code=401, detail={"error": {"code": "unauthorized"}})


async def current_user(request: Request, token: str = Depends(oauth2_scheme)
                       ) -> AuthenticatedUser:
    auth = request.app.state.services.auth
    try:
        user_id = auth.verify_token(token)
    except InvalidToken:
        raise _unauthorized() from None
    user = await auth.load_user(user_id)
    if user is None:  # load_user returns None for unknown AND inactive users
        raise _unauthorized()
    return user


def services(request: Request) -> Any:
    return request.app.state.services


def today(request: Request) -> Any:
    settings = request.app.state.settings
    return datetime.now(settings.tz).date()
