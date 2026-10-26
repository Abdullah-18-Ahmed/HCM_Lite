# Deploying HCM Lite — Railway

HCM Lite is a **FastAPI backend + single-page UI**, so it needs a host that runs Python.
Railway runs a persistent server and gives you a **Volume** (persistent disk), so the app's
own SQLite database and embedded Qdrant index can live there — no external databases needed.

> **Cost:** Railway has no permanent free tier — new accounts get a one-time ~$5 trial
> credit, then the Hobby plan is ~$5/month. Verify current pricing at
> <https://railway.com/pricing>.

The repo already contains `railway.toml` (build + start command + health check) and
`.python-version` (pins Python 3.12), so Railway auto-detects everything.

---

## Step 1 — Create the project from GitHub

1. Go to <https://railway.com> → sign in **with GitHub**.
2. **New Project** → **Deploy from GitHub repo** → pick **`HCM_Lite`**.
3. Railway starts a build immediately. It will likely fail the first time until you add the
   volume and env vars below — that's expected; finish the next steps, then redeploy.

## Step 2 — Add a persistent Volume

1. Open the service → **Variables/Settings** → **Volumes** → **New Volume**.
2. Set the **Mount path** to:
   ```
   /data
   ```
3. Save. This disk now survives restarts and redeploys.

## Step 3 — Set environment variables

In the service → **Variables**, add:

| Variable | Value |
|---|---|
| `OPENAI_API_KEY` | your OpenAI key |
| `OPENAI_MODEL` | `gpt-4o-mini` (or the model you use) |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `API_JWT_SECRET` | a random string ≥ 32 chars (see below) |
| `DATABASE_URL` | `sqlite+aiosqlite:////data/hcm_lite.db` |
| `VECTOR_STORE_PATH` | `/data/qdrant` |

> The four slashes in `sqlite+aiosqlite:////data/hcm_lite.db` are correct — they mean the
> absolute path `/data/...` (your Volume mount).

Generate the JWT secret locally and paste the output:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Step 4 — Deploy & get a public URL

1. Trigger a redeploy (Railway auto-redeploys when you change variables, or use **Deploy**).
   The start command runs `alembic upgrade head` (creates the schema on the Volume), then
   `uvicorn`.
2. Service → **Settings** → **Networking** → **Generate Domain** to get a public URL like
   `https://hcm-lite-production.up.railway.app`.

## Step 5 — First visit

1. Open the URL (first load ~10–15s while Qdrant initializes — normal).
2. The database is empty, so the UI shows a **"Create admin"** screen. Enter your email /
   name / password — that becomes your login. (No seeding needed.)
3. To enable the assistant's policy Q&A, index the HR docs once. Install the Railway CLI
   (`npm i -g @railway/cli`), then from the repo:
   ```powershell
   railway link        # pick this project/service
   railway run python -m hcm_lite.rag.ingest ingest
   ```
   (Or open a shell on the service from the dashboard and run the same command.)

Because SQLite + Qdrant sit on the Volume, you do Step 5 **once** — it persists.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build uses the wrong Python | `.python-version` pins 3.12; confirm it's in the repo root |
| App starts but data resets each deploy | the Volume isn't mounted at `/data`, or `DATABASE_URL`/`VECTOR_STORE_PATH` don't point at `/data` |
| `must be an async SQLAlchemy URL` at startup | `DATABASE_URL` must start with `sqlite+aiosqlite://` (or `postgresql+asyncpg://`) |
| Missing key error at startup | set `OPENAI_API_KEY` |
| Health check fails | `/health` needs the app running; check the deploy logs for the real error |
| Assistant finds no policies | run `python -m hcm_lite.rag.ingest ingest` (Step 5) |

## Alternative: Railway Postgres instead of SQLite-on-a-Volume

Add a **Postgres** database from Railway's **New → Database**, then set `DATABASE_URL` to its
async form, e.g. `postgresql+asyncpg://user:pass@host:port/dbname` (Railway gives you the
connection parts under the Postgres service's **Variables** — note the app needs the
`+asyncpg` driver prefix, not Railway's default `postgresql://`). The Volume is then only
needed for Qdrant (`VECTOR_STORE_PATH=/data/qdrant`).
