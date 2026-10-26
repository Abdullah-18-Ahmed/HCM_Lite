"""T009: Settings per contracts/configuration.md (constitution Art. XV)."""

from __future__ import annotations

import httpx
import openai
import pytest

from hcm_lite.config import Settings, get_settings, load_settings, verify_models
from hcm_lite.errors import ConfigurationError, ModelServiceError

JWT_SECRET = "j" * 48
API_KEY = "sk-test-very-secret-key"

REQUIRED = {
    "OPENAI_API_KEY": API_KEY,
    "OPENAI_MODEL": "gpt-test",
    "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
    "API_JWT_SECRET": JWT_SECRET,
}

ALL_VARS = [
    *REQUIRED,
    "DATABASE_URL", "API_TOKEN_MINUTES", "API_CORS_ORIGINS", "SESSION_IDLE_MINUTES",
    "LOGIN_MAX_FAILURES", "LOGIN_LOCK_MINUTES", "VECTOR_STORE_PROVIDER", "VECTOR_STORE_PATH",
    "VECTOR_STORE_URL", "VECTOR_STORE_API_KEY", "VECTOR_STORE_COLLECTION", "RAG_TOP_K",
    "RAG_SIMILARITY_THRESHOLD", "RAG_CHUNK_SIZE", "RAG_CHUNK_OVERLAP", "DOCUMENTS_DIR",
    "APP_TIMEZONE", "LATE_GRACE_MINUTES", "AGENT_MAX_TURNS", "MODEL_TIMEOUT_SECONDS",
]


@pytest.fixture
def env(monkeypatch, tmp_path):
    for name in ALL_VARS:
        monkeypatch.delenv(name, raising=False)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path))
    return monkeypatch


def load() -> Settings:
    return load_settings(env_file=None)


def test_valid_env_loads_with_defaults(env):
    s = load()
    assert s.openai_model == "gpt-test"
    assert s.database_url.get_secret_value() == "sqlite+aiosqlite:///./data/hcm_lite.db"
    assert s.api_token_minutes == 60
    assert s.session_idle_minutes == 60
    assert s.login_max_failures == 5
    assert s.login_lock_minutes == 15
    assert s.vector_store_provider == "qdrant"
    assert s.vector_store_collection == "hr_documents"
    assert s.rag_top_k == 5
    assert s.rag_similarity_threshold == pytest.approx(0.35)
    assert (s.rag_chunk_size, s.rag_chunk_overlap) == (800, 120)
    assert s.app_timezone == "UTC"
    assert s.late_grace_minutes == 0
    assert s.agent_max_turns == 8
    assert s.model_timeout_seconds == 30
    assert s.cors_origins == []


@pytest.mark.parametrize("name", list(REQUIRED))
def test_missing_required_var_names_it(env, name):
    env.delenv(name)
    with pytest.raises(ConfigurationError) as exc:
        load()
    assert name in str(exc.value)
    assert name in exc.value.variables


@pytest.mark.parametrize("name", list(REQUIRED))
def test_empty_required_var_counts_as_missing(env, name):
    env.setenv(name, "")
    with pytest.raises(ConfigurationError) as exc:
        load()
    assert name in exc.value.variables


def test_short_jwt_secret_rejected_without_echoing_it(env):
    env.setenv("API_JWT_SECRET", "short-secret-31-chars-xxxxxxxxx")
    with pytest.raises(ConfigurationError) as exc:
        load()
    assert exc.value.variables == ["API_JWT_SECRET"]
    assert "short-secret" not in str(exc.value)


def test_jwt_secret_exactly_32_chars_accepted(env):
    env.setenv("API_JWT_SECRET", "x" * 32)
    assert load().api_jwt_secret.get_secret_value() == "x" * 32


@pytest.mark.parametrize(
    "url",
    ["sqlite+aiosqlite:///./data/x.db", "sqlite+aiosqlite:///:memory:",
     "postgresql+asyncpg://u:p@localhost/hcm"],
)
def test_async_database_urls_accepted(env, url):
    env.setenv("DATABASE_URL", url)
    assert load().database_url.get_secret_value() == url


@pytest.mark.parametrize(
    "url",
    ["sqlite:///./data/x.db", "postgresql://user:hunter2@db/hcm", "mysql+aiomysql://x/y",
     "not a url"],
)
def test_sync_or_unknown_database_url_rejected_without_echoing_it(env, url):
    env.setenv("DATABASE_URL", url)
    with pytest.raises(ConfigurationError) as exc:
        load()
    assert exc.value.variables == ["DATABASE_URL"]
    assert url not in str(exc.value)
    assert "hunter2" not in str(exc.value)


def test_secrets_masked_in_repr_and_str(env):
    env.setenv("DATABASE_URL", "postgresql+asyncpg://u:dbpassword@h/hcm")
    env.setenv("VECTOR_STORE_API_KEY", "qdrant-key-value")
    s = load()
    for text in (repr(s), str(s)):
        for secret in (API_KEY, JWT_SECRET, "dbpassword", "qdrant-key-value"):
            assert secret not in text


@pytest.mark.parametrize(
    ("name", "bad", "good"),
    [
        ("API_TOKEN_MINUTES", ["4", "481"], ["5", "480"]),
        ("SESSION_IDLE_MINUTES", ["4", "481"], ["5", "480"]),
        ("LOGIN_MAX_FAILURES", ["0", "21"], ["1", "20"]),
        ("LOGIN_LOCK_MINUTES", ["0", "1441"], ["1", "1440"]),
        ("RAG_TOP_K", ["0", "21"], ["1", "20"]),
        ("RAG_SIMILARITY_THRESHOLD", ["-0.01", "1.01"], ["0", "1"]),
        ("LATE_GRACE_MINUTES", ["-1", "121"], ["0", "120"]),
        ("AGENT_MAX_TURNS", ["0", "21"], ["1", "20"]),
        ("MODEL_TIMEOUT_SECONDS", ["4", "121"], ["5", "120"]),
        ("VECTOR_STORE_PROVIDER", ["chroma"], ["qdrant"]),
        ("VECTOR_STORE_COLLECTION", ["HR-Docs", "a b", ""], ["hr_documents", "docs2"]),
        ("APP_TIMEZONE", ["Not/AZone", "Mars/Base", "Asia"],
         ["UTC", "Asia/Karachi", "Europe/London"]),
    ],
)
def test_range_validators(env, name, bad, good):
    for value in bad:
        env.setenv(name, value)
        if value == "":  # empty means "use the default", which is valid
            load()
            continue
        with pytest.raises(ConfigurationError) as exc:
            load()
        assert exc.value.variables == [name], value
    for value in good:
        env.setenv(name, value)
        load()


def test_iana_timezone_resolves_via_zoneinfo(env):
    from zoneinfo import ZoneInfo

    env.setenv("APP_TIMEZONE", "Asia/Karachi")
    s = load()
    assert s.app_timezone == "Asia/Karachi"
    assert s.tz == ZoneInfo("Asia/Karachi")
    env.setenv("APP_TIMEZONE", "UTC")
    assert load().tz == ZoneInfo("UTC")


def test_chunk_overlap_must_be_less_than_size(env):
    env.setenv("RAG_CHUNK_SIZE", "200")
    env.setenv("RAG_CHUNK_OVERLAP", "200")
    with pytest.raises(ConfigurationError) as exc:
        load()
    assert "RAG_CHUNK_OVERLAP" in exc.value.variables
    env.setenv("RAG_CHUNK_OVERLAP", "199")
    load()


def test_documents_dir_must_exist(env, tmp_path):
    env.setenv("DOCUMENTS_DIR", str(tmp_path / "missing"))
    with pytest.raises(ConfigurationError) as exc:
        load()
    assert exc.value.variables == ["DOCUMENTS_DIR"]


def test_cors_origins_comma_separated(env):
    env.setenv("API_CORS_ORIGINS", "http://localhost:3000, http://127.0.0.1:3000")
    assert load().cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_several_errors_reported_together(env):
    env.delenv("OPENAI_MODEL")
    env.setenv("RAG_TOP_K", "99")
    with pytest.raises(ConfigurationError) as exc:
        load()
    assert set(exc.value.variables) == {"OPENAI_MODEL", "RAG_TOP_K"}


def test_get_settings_is_cached(env, tmp_path):
    env.chdir(tmp_path)  # no .env here; values come from the patched environment
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------- verify_models


def _request() -> httpx.Request:
    return httpx.Request("GET", "https://api.openai.test/v1/models/x")


class FakeModels:
    def __init__(self, missing=(), error=None):
        self.missing, self.error, self.calls = set(missing), error, []

    async def retrieve(self, model):
        self.calls.append(model)
        if self.error is not None:
            raise self.error
        if model in self.missing:
            raise openai.NotFoundError(
                "not found", response=httpx.Response(404, request=_request()), body=None
            )
        return object()


class FakeClient:
    def __init__(self, models):
        self.models = models


async def test_verify_models_checks_both_models(env):
    fake = FakeModels()
    await verify_models(load(), client=FakeClient(fake))
    assert fake.calls == ["gpt-test", "text-embedding-3-small"]


@pytest.mark.parametrize(
    ("missing", "var"),
    [("gpt-test", "OPENAI_MODEL"), ("text-embedding-3-small", "OPENAI_EMBEDDING_MODEL")],
)
async def test_verify_models_unknown_model_names_variable(env, missing, var):
    with pytest.raises(ConfigurationError) as exc:
        await verify_models(load(), client=FakeClient(FakeModels(missing=[missing])))
    assert exc.value.variables == [var]


async def test_verify_models_bad_key_names_api_key_without_value(env):
    error = openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=_request()), body=None
    )
    with pytest.raises(ConfigurationError) as exc:
        await verify_models(load(), client=FakeClient(FakeModels(error=error)))
    assert exc.value.variables == ["OPENAI_API_KEY"]
    assert API_KEY not in str(exc.value)


async def test_verify_models_connection_failure_is_model_service_error(env):
    error = openai.APIConnectionError(request=_request())
    with pytest.raises(ModelServiceError):
        await verify_models(load(), client=FakeClient(FakeModels(error=error)))
