# Contract: Command-Line Tools

## Database

| Command | Behaviour | Exit |
|---------|-----------|------|
| `alembic upgrade head` | Apply all pending migrations (`hcm_lite/db/migrations/versions/`) | 0 ok; non-zero on failure (Alembic) |
| `python -m hcm_lite.db status` | Current vs head revision, and row counts per table | 0; 1 = DB unreadable |
| `python -m hcm_lite.db seed [--force] [--reset]` | Create demo data (research D-13). Refuses when non-demo rows exist unless `--force`; `--reset` deletes `is_demo = 1` rows first; refuses unless the DB is at head; prints demo credentials | 0 ok; 2 refused; 1 error |
| `python -m hcm_lite.db create-user --username U --role R --employee-id E` | Create a non-demo account; the password is read from a prompt (never an argument) | 0 / 1 |

`alembic.ini` reads the URL from `DATABASE_URL` (`env.py` uses `get_settings()`); there is no URL in
the ini file. Re-running `alembic upgrade head` at head is a no-op.

## Documents: `python -m hcm_lite.rag.ingest <command>`

| Command | Behaviour | Exit |
|---------|-----------|------|
| `ingest` (default) | Incremental: load new, update changed, skip unchanged, remove deleted files from `DOCUMENTS_DIR` | 0; 2 = some rejected; 1 = fatal |
| `rebuild` | Drop and recreate the collection, then a full ingest | as above |
| `status` | Point count, embedding model, last report | 0 / 1 |
| `clear --yes [--allow-remote]` | Delete the dev collection and registry; refuses without `--yes`, and refuses for a remote URL without `--allow-remote` | 0 / 1 |

Options: `--source PATH`, `--json`. The report goes to `.ingest/last_report.json` (paths and
statuses only, no document text).

## Servers

| Command | Purpose |
|---------|---------|
| `chainlit run app.py` | Chat + dashboard UI on http://localhost:8000 |
| `uvicorn hcm_lite.api.main:app --port 8001` | REST API on http://localhost:8001 (`/docs` for OpenAPI) |

Both refuse to start if the DB is not at the head revision, or if required settings are missing.
