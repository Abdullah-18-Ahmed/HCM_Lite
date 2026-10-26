# Deploying HCM Lite — Render (free tier)

HCM Lite is a **FastAPI backend + single-page UI**, so it needs a host that runs Python
(not GitHub Pages / Vercel, which only do static files or short serverless functions).
Render's free plan runs a real `uvicorn` server, so the whole app works. This guide uses the
`render.yaml` blueprint in the repo root.

## Steps

1. Go to <https://dashboard.render.com> and sign in **with GitHub**.
2. **New +** → **Blueprint**.
3. Pick the **`HCM_Lite`** repo → **Apply**. Render reads `render.yaml` and creates the
   `hcm-lite` web service on the **free** plan.
4. Set the one secret it asks for:
   - **`OPENAI_API_KEY`** = your OpenAI key.
   - (`API_JWT_SECRET` is auto-generated; everything else has defaults.)
5. **Create / Deploy.** The build installs dependencies and runs the DB migration.

When it finishes you get a live URL like **`https://hcm-lite-xxxx.onrender.com/`**
(API docs at `/docs`).

## First visit

- **First load takes ~10–15s** while the embedded Qdrant store initializes — normal.
- The database starts empty, so the UI shows a **"Create admin" setup screen**. Fill in your
  email / name / password — that becomes your login. (No seed step needed.)
- Sign in, and you're in the dashboard. From the admin account you can add more users.

### Optional: enable policy Q&A (RAG)
The AI assistant's document search needs the HR documents indexed once. Open the service's
**Shell** tab in Render and run:
```bash
python -m hcm_lite.rag.ingest ingest
```

## ⚠️ Free-tier limitations (important)

The free plan has **no persistent disk**, and it **sleeps after ~15 minutes of inactivity**.
When it sleeps (or on any redeploy) the container's filesystem is wiped, which means:

- The SQLite database resets → **the admin account and all data are lost**.
- The Qdrant index resets → you'd re-run `ingest`.

On the next visit you'll just see the setup screen again and recreate the admin. That's fine
for showing a quick demo, but **not** for a link you want to share and keep working.

The first request after it sleeps also takes ~30–60s to wake up.

## Make it persistent — still free

Point the app at free hosted databases instead of the local files (your repo already
supports both — see `.env.example`). Then the web service is stateless and nothing resets:

1. **Postgres** — create a free DB at **Neon** (neon.tech) or **Supabase**. In Render, add
   env var `DATABASE_URL` = your async URL, e.g.
   `postgresql+asyncpg://USER:PASS@HOST/DBNAME`.
2. **Qdrant** — create a free cluster at **Qdrant Cloud**. In Render, add
   `VECTOR_STORE_URL` and `VECTOR_STORE_API_KEY` (leave `VECTOR_STORE_PATH` unset).

Redeploy, create your admin once, run `ingest` once — and it stays put across restarts.
