"""Application settings (contracts/configuration.md, constitution Art. XV).

Read settings only through :func:`get_settings`. A missing or invalid value raises
:class:`~hcm_lite.errors.ConfigurationError` naming the variable, never its value.
"""

from __future__ import annotations

import re
from datetime import tzinfo
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pydantic
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hcm_lite.errors import ConfigurationError, ModelServiceError

MIN_JWT_SECRET_LENGTH = 32
ASYNC_DB_URL_PREFIXES = ("sqlite+aiosqlite://", "postgresql+asyncpg://")
REQUIRED_SECRETS = ("openai_api_key", "chainlit_auth_secret", "api_jwt_secret")


def _resolve_timezone(name: str) -> tzinfo:
    # Any IANA zone; on Windows the database comes from the ``tzdata`` package.
    return ZoneInfo(name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # an empty value counts as unset
        case_sensitive=False,
        extra="ignore",
    )

    # --- OpenAI ---
    openai_api_key: SecretStr
    openai_model: str = Field(min_length=1)
    openai_embedding_model: str = Field(min_length=1)

    # --- Database ---
    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///./data/hcm_lite.db")

    # --- Auth ---
    chainlit_auth_secret: SecretStr
    api_jwt_secret: SecretStr
    api_token_minutes: int = Field(60, ge=5, le=480)
    api_cors_origins: str = ""
    session_idle_minutes: int = Field(60, ge=5, le=480)
    login_max_failures: int = Field(5, ge=1, le=20)
    login_lock_minutes: int = Field(15, ge=1, le=1440)

    # --- Vector store ---
    vector_store_provider: Literal["qdrant"] = "qdrant"
    vector_store_path: str = ".qdrant"
    vector_store_url: str = ""
    vector_store_api_key: SecretStr = SecretStr("")
    vector_store_collection: str = Field("hr_documents", pattern=r"^[a-z0-9_]+$")

    # --- RAG ---
    rag_top_k: int = Field(5, ge=1, le=20)
    rag_similarity_threshold: float = Field(0.35, ge=0.0, le=1.0)
    rag_chunk_size: int = Field(800, ge=1)
    rag_chunk_overlap: int = Field(120, ge=0)
    documents_dir: Path = Path("data/demo/documents")

    # --- Application ---
    app_timezone: str = "UTC"
    late_grace_minutes: int = Field(0, ge=0, le=120)
    agent_max_turns: int = Field(8, ge=1, le=20)
    model_timeout_seconds: int = Field(30, ge=5, le=120)

    @field_validator(*REQUIRED_SECRETS)
    @classmethod
    def _secret_not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("is required")
        return value

    @field_validator("api_jwt_secret")
    @classmethod
    def _jwt_secret_length(cls, value: SecretStr) -> SecretStr:
        # PyJWT only warns on short HMAC keys (research.md, T007), so enforce it here.
        if len(value.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"must be at least {MIN_JWT_SECRET_LENGTH} characters")
        return value

    @field_validator("database_url")
    @classmethod
    def _async_database_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(ASYNC_DB_URL_PREFIXES):
            raise ValueError(
                "must be an async SQLAlchemy URL (sqlite+aiosqlite:// or postgresql+asyncpg://)"
            )
        return value

    @field_validator("documents_dir")
    @classmethod
    def _documents_dir_exists(cls, value: Path) -> Path:
        if not value.is_dir():
            raise ValueError("directory does not exist")
        return value

    @field_validator("app_timezone")
    @classmethod
    def _iana_timezone(cls, value: str) -> str:
        try:
            _resolve_timezone(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError("must be an IANA time zone name") from None
        return value

    @model_validator(mode="after")
    def _overlap_below_size(self) -> Settings:
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be less than RAG_CHUNK_SIZE")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def tz(self) -> tzinfo:
        return _resolve_timezone(self.app_timezone)


_VAR_IN_MESSAGE = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")


def _to_configuration_error(exc: pydantic.ValidationError) -> ConfigurationError:
    variables: list[str] = []
    parts: list[str] = []
    for err in exc.errors(include_input=False, include_url=False):
        loc = err.get("loc") or ()
        if loc:
            name = str(loc[0]).upper()
            reason = "is required" if err["type"] == "missing" else err["msg"]
        else:  # model-level validator: the message names the variable itself
            found = _VAR_IN_MESSAGE.findall(err["msg"])
            name = found[0] if found else "CONFIGURATION"
            reason = err["msg"]
        reason = reason.removeprefix("Value error, ")
        if name not in variables:
            variables.append(name)
        parts.append(reason if reason.startswith(name) else f"{name}: {reason}")
    message = "Invalid configuration: " + "; ".join(parts)
    return ConfigurationError(message, variables=variables)


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    """Build settings from the environment (and ``env_file`` if given)."""
    try:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    except pydantic.ValidationError as exc:
        raise _to_configuration_error(exc) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


async def verify_models(settings: Settings, client: Any | None = None) -> None:
    """Check OPENAI_MODEL and OPENAI_EMBEDDING_MODEL against the OpenAI Models API."""
    import openai

    if client is None:
        client = openai.AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.model_timeout_seconds,
        )
    checks = (
        ("OPENAI_MODEL", settings.openai_model),
        ("OPENAI_EMBEDDING_MODEL", settings.openai_embedding_model),
    )
    for variable, model in checks:
        try:
            await client.models.retrieve(model)
        except openai.NotFoundError:
            raise ConfigurationError(
                f"{variable} names a model that is not available to this API key",
                variables=[variable],
            ) from None
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            raise ConfigurationError(
                "OPENAI_API_KEY was rejected by the model service", variables=["OPENAI_API_KEY"]
            ) from None
        except openai.OpenAIError:
            raise ModelServiceError("The model service could not be reached") from None
