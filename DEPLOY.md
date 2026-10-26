# Deploying HCM Lite (Render)

HCM Lite is a **FastAPI backend + single-page UI** — it needs a host that runs Python.
GitHub Pages can only serve static files, so it **cannot** run this app. Render is the
simplest host that can; this guide uses the `render.yaml` blueprint in the repo root.

> Any Python/container host works (Railway, Fly.io, Cloud Run, Azure App Service). The
> start command is always: `uvicorn hcm_lite.api.main:app --host 0.0.0.0 --port $PORT`.

## 1. Deploy with the blueprint

1. Go to <https://dashboard.render.com> and sign in with GitHub.
2. **New +** → **Blueprint** → select the **`HCM_Lite`** repo → **Apply**.
3. Render reads `render.yaml` and creates one web service (`hcm-lite`).
4. When prompted, set the one secret it needs:
   - **`OPENAI_API_KEY`** — your OpenAI key (this one is not stored in the repo).
   - `API_JWT_SECRET` is generated automatically; the rest have sensible defaults.
5. Click **Create / Deploy**. First build installs deps and runs the DB migration.

Your site will be live at `https://hcm-lite-XXXX.onrender.com/` (API docs at `/docs`).

> **First load takes ~10–15s** while embedded Qdrant initializes — that's normal.

## 2. Seed demo data + index documents (one time)

The app boots with an empty database. After the first deploy succeeds, open the service's
**Shell** tab in Render and run:

```bash
python -m hcm_lite.db seed             # creates demo users — PRINTS passwords ONCE, copy them
python -m hcm_lite.rag.ingest ingest   # indexes the demo HR policy documents
```

Copy the printed demo passwords (`employee` / `manager` / `hr_admin`) — they aren't stored
anywhere. Then sign in on the live site.

## 3. Plans & data persistence

| Plan | Cost | Data persistence |
|------|------|------------------|
| **Starter** (default in `render.yaml`) | paid | ✅ Disk at `/var/data` keeps SQLite + Qdrant across restarts/deploys |
| **Free** | free | ⚠️ No disks allowed — **delete the `disk:` block** in `render.yaml` and the `DATABASE_URL`/`VECTOR_STORE_PATH` lines. Data (including seeded users) resets on every restart, and the service sleeps after inactivity. Fine for a quick demo; re-run the seed/ingest after each cold start. |

## 4. Scaling beyond the demo

For real multi-user load, swap the embedded stores for networked ones (both already
supported via env vars — see `.env.example`):

- **Postgres** instead of SQLite: set `DATABASE_URL` to your async Postgres URL
  (`postgresql+asyncpg://...`). `asyncpg` is already in `requirements.txt`.
- **Qdrant server** instead of embedded: set `VECTOR_STORE_URL` and `VECTOR_STORE_API_KEY`,
  and leave `VECTOR_STORE_PATH` unset.

Then the web service is stateless and the disk block can be removed entirely.
