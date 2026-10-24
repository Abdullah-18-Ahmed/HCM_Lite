# Contract: Configuration (`.env`)

Loaded by `hcm_lite/config.py` (`pydantic-settings` + `python-dotenv`). `.env` is git-ignored;
`.env.example` lists names only. Invalid or missing required values raise `ConfigurationError` at
startup, and the error names the variable but never prints secret values.

| Variable | Required | Default | Validation |
|----------|:-------:|---------|------------|
| OPENAI_API_KEY | yes | — | non-empty; masked in all output |
| OPENAI_MODEL | yes | — | availability checked at startup |
| OPENAI_EMBEDDING_MODEL | yes | — (example: `text-embedding-3-small`) | availability checked |
| CHAINLIT_AUTH_SECRET | yes | — | generate with `chainlit create-secret` |
| VECTOR_STORE_PROVIDER | no | `qdrant` | only `qdrant` is accepted |
| VECTOR_STORE_PATH | no | `.qdrant` | used when URL is empty (local embedded mode) |
| VECTOR_STORE_URL | no | empty | when set → Qdrant server mode |
| VECTOR_STORE_API_KEY | no | empty | Qdrant Cloud / secured server |
| VECTOR_STORE_COLLECTION | no | `hr_documents` | `[a-z0-9_]+` |
| RAG_TOP_K | no | `5` | 1–20 |
| RAG_SIMILARITY_THRESHOLD | no | `0.35` | 0.0–1.0 |
| RAG_CHUNK_SIZE | no | `800` | 200–4000 |
| RAG_CHUNK_OVERLAP | no | `120` | 0 ≤ overlap < chunk size |
| DOCUMENTS_DIR | no | `data/demo/documents` | must exist |
| HR_DATA_DIR | no | `data/demo/records` | must exist |
| PERSONAS_FILE | no | `data/demo/personas.json` | must exist |
| APP_TIMEZONE | no | `UTC` | IANA name |
| LATE_GRACE_MINUTES | no | `0` | 0–120 |
| AGENT_MAX_TURNS | no | `8` | 1–20 |
| MODEL_TIMEOUT_SECONDS | no | `30` | 5–120 |
| DEMO_MODE | no | auto | auto = true if any loaded source has the demo label |
