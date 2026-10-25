"""Authentication (contracts/services.md AuthService, research D-05, FR-001–004).

One ``AuthService`` serves both entry points (Chainlit ``chat`` and FastAPI ``api``). Failures
always return a generic ``None``; the audit records which case it was.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from hcm_lite.db.repositories import EmployeeRepo, LoginFailureRepo, UserRepo
from hcm_lite.models.domain import (
    AuditAction,
    AuditOutcome,
    AuthenticatedUser,
    Channel,
    UserRecord,
)
from hcm_lite.services.audit import Auditor
from hcm_lite.services.passwords import dummy_verify, verify_password
from hcm_lite.services.tokens import TokenService

Clock = Callable[[], datetime]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class AuthService:
    def __init__(
        self,
        session_factory: Any,
        *,
        auditor: Auditor,
        tokens: TokenService,
        max_failures: int = 5,
        lock_minutes: int = 15,
        clock: Clock | None = None,
    ) -> None:
        self._sf = session_factory
        self._auditor = auditor
        self.tokens = tokens
        self._max_failures = max_failures
        self._lock = timedelta(minutes=lock_minutes)
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def from_settings(cls, settings: Any, session_factory: Any, auditor: Auditor,
                      *, clock: Clock | None = None) -> AuthService:
        return cls(session_factory, auditor=auditor,
                   tokens=TokenService.from_settings(settings, clock=clock),
                   max_failures=settings.login_max_failures,
                   lock_minutes=settings.login_lock_minutes, clock=clock)

    # ------------------------------------------------------------------ sign-in

    async def _fail(self, action: AuditAction, channel: Channel, actor: str | None = None
                    ) -> None:
        await self._auditor.audit(action, AuditOutcome.DENIED, actor=actor, channel=channel)

    async def authenticate(self, username: str, password: str,
                           channel: Channel | str) -> AuthenticatedUser | None:
        channel = Channel(channel)
        now = self._clock()
        if not isinstance(username, str) or not isinstance(password, str) or not username:
            dummy_verify("")
            await self._fail(AuditAction.LOGIN_FAILED, channel)
            return None
        async with self._sf() as session:
            user = await UserRepo(session).get_by_username(username.strip())
        if user is None:
            dummy_verify(password)  # timing parity for unknown usernames
            await self._fail(AuditAction.LOGIN_FAILED, channel)
            return None
        if user.locked_until is not None and _aware(user.locked_until) > now:
            dummy_verify(password)
            await self._fail(AuditAction.ACCOUNT_LOCKED, channel, user.id)
            return None
        # Stripping is normalization for copy-paste artifacts, not a weakening: generated
        # passwords never contain leading/trailing whitespace.
        if not verify_password(password.strip(), user.password_hash):
            locked = await self._record_failure(user, now)
            await self._fail(AuditAction.LOGIN_FAILED, channel, user.id)
            if locked:
                await self._fail(AuditAction.ACCOUNT_LOCKED, channel, user.id)
            return None
        if not user.active:
            await self._fail(AuditAction.LOGIN_FAILED, channel, user.id)
            return None
        async with self._sf() as session, session.begin():
            await LoginFailureRepo(session).clear(user.id)
            if user.locked_until is not None:
                await UserRepo(session).set_locked_until(user.id, None)
        loaded = await self.load_user(user.id)
        if loaded is None:
            await self._fail(AuditAction.LOGIN_FAILED, channel, user.id)
            return None
        await self._auditor.audit(AuditAction.LOGIN_SUCCESS, AuditOutcome.OK, actor=user.id,
                                  channel=channel)
        return loaded

    async def _record_failure(self, user: UserRecord, now: datetime) -> bool:
        """Store the failure; lock the account at ``max_failures`` within the window."""
        async with self._sf() as session, session.begin():
            failures = LoginFailureRepo(session)
            await failures.add(user.id, now)
            count = await failures.count_since(user.id, now - self._lock)
            if count >= self._max_failures:
                await UserRepo(session).set_locked_until(user.id, now + self._lock)
                return True
        return False

    async def load_user(self, user_id: str) -> AuthenticatedUser | None:
        """Fresh identity and role from the DB; None if unknown or inactive."""
        if not isinstance(user_id, str) or not user_id:
            return None
        async with self._sf() as session:
            user = await UserRepo(session).get(user_id)
            if user is None or not user.active:
                return None
            employee = await EmployeeRepo(session).get(user.employee_id)
        if employee is None:
            return None
        return AuthenticatedUser(user_id=user.id, username=user.username, role=user.role,
                                 employee_id=user.employee_id, display_name=employee.full_name,
                                 department=employee.department)

    # ------------------------------------------------------------------ tokens (API)

    def issue_token(self, user: AuthenticatedUser) -> tuple[str, int]:
        return self.tokens.issue(user.user_id)

    def verify_token(self, token: str) -> str:
        return self.tokens.verify(token)

    async def revoke_token(self, token: str) -> None:
        user_id = self.tokens.verify(token)
        self.tokens.revoke(token)
        await self._auditor.audit(AuditAction.LOGOUT, AuditOutcome.OK, actor=user_id,
                                  channel=Channel.API)

    # ------------------------------------------------------------------ chat logout

    async def record_logout(self, user: AuthenticatedUser | str,
                            reason: Literal["logout", "session_expired"] = "logout") -> None:
        action = (AuditAction.SESSION_EXPIRED if reason == "session_expired"
                  else AuditAction.LOGOUT)
        actor = user if isinstance(user, str) else user.user_id
        await self._auditor.audit(action, AuditOutcome.OK, actor=actor, channel=Channel.CHAT)
