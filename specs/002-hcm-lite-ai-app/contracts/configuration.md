# Contract: Configuration (`.env`)

Loaded by `hcm_lite/config.py` (pydantic-settings + python-dotenv). `.env` is git-ignored;
`.env.example` holds names and placeholders only. A missing or invalid required value raises
`ConfigurationError` naming the variable, never its value (constitution Art. XV).

| Variable | Req. | Default | Validation |
|----------|:---:|---------|------------|
| OPENAI_API_KEY | yes | — | SecretStr |
| OPENAI_MODEL | yes | — | checked against the Models API at startup |
| OPENAI_EMBEDDING_MODEL | yes | — (example `text-embedding-3-small`) | checked at startup |
| DATABASE_URL | no | `sqlite+aiosqlite:///./data/hcm_lite.db` | SecretStr (may hold credentials for a future server DB); must be an async SQLAlchemy URL |
| CHAINLIT_AUTH_SECRET | yes | — | from `chainlit create-secret` |
| API_JWT_SECRET | yes | — | ≥ 32 chars; generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| API_TOKEN_MINUTES | no | `60` | 5–480 |
| API_CORS_ORIGINS | no | empty | comma-separated origins; empty = CORS off |
| SESSION_IDLE_MINUTES | no | `60` | 5–480 |
| LOGIN_MAX_FAILURES | no | `5` | 1–20 |
| LOGIN_LOCK_MINUTES | no | `15` | 1–1440 |
| VECTOR_STORE_PROVIDER | no | `qdrant` | only `qdrant` |
| VECTOR_STORE_PATH | no | `.qdrant` | used when the URL is empty |
| VECTOR_STORE_URL | no | empty | Qdrant server mode |
| VECTOR_STORE_API_KEY | no | empty | SecretStr |
| VECTOR_STORE_COLLECTION | no | `hr_documents` | `[a-z0-9_]+` |
| RAG_TOP_K | no | `5` | 1–20 |
| RAG_SIMILARITY_THRESHOLD | no | `0.35` | 0–1 |
| RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP | no | `800` / `120` | overlap < size |
| DOCUMENTS_DIR | no | `data/demo/documents` | exists |
| APP_TIMEZONE | no | `UTC` | IANA |
| LATE_GRACE_MINUTES | no | `0` | 0–120 |
| AGENT_MAX_TURNS | no | `8` | 1–20 |
| MODEL_TIMEOUT_SECONDS | no | `30` | 5–120 |
