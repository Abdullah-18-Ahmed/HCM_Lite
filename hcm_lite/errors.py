"""Error taxonomy (research D-11, contracts/services.md).

Each error has a ``category`` used by the runner (contracts/agent-tools.md) and the API status
mapping (contracts/api.md). Messages are safe to show: they never carry secret values,
passwords, message text, document text or employee names.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime


class HCMError(Exception):
    """Base class for every application error."""

    category: str = "internal"

    def __init__(self, message: str = "", *, category: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if category is not None:
            self.category = category


class ConfigurationError(HCMError):
    """Missing or invalid configuration. Names the variables, never their values."""

    category = "configuration"

    def __init__(self, message: str = "", *, variables: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.variables: list[str] = list(variables)


class DatabaseError(HCMError):
    category = "database"


class RetrievalError(HCMError):
    category = "retrieval"


class ModelServiceError(HCMError):
    category = "model_service"


class AccessDenied(HCMError):
    category = "access_denied"

    def __init__(self, capability: str) -> None:
        super().__init__(f"Access denied: {capability}")
        self.capability = capability


class ValidationError(HCMError):
    category = "invalid_input"

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


class NotFound(HCMError):
    category = "not_found"


class AccountLocked(HCMError):
    category = "account_locked"

    def __init__(self, until: datetime) -> None:
        super().__init__("Account temporarily locked")
        self.until = until


class InvalidToken(HCMError):
    category = "invalid_token"
