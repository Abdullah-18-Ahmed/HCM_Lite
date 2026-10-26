# Deploying HCM Lite — Render free (for a demo/showcase)

HCM Lite is a **FastAPI backend + single-page UI**, so it needs a host that runs Python
(GitHub Pages / Vercel can't — they only serve static files or short serverless functions).
Render's free plan runs a real `uvicorn` server, so the whole app works, including the AI
assistant. This guide uses the `render.yaml` blueprint in the repo root.

> **Free, no credit card.** The only trade-off: the service sleeps after ~15 min idle and
> takes ~30–60s to wake on the next visit — fine for showing a project.

## Deploy (≈5 minutes)

1. Go to <https://dashboard.render.com> and sign in **with GitHub**.
2. **New +** → **Blueprint**.
3. Pick the **`HCM_Lite`** repo → **Apply**. Render reads `render.yaml` and creates the
   `hcm-lite` web service on the **free** plan.
4. When prompted, set the one secret:
   - **`OPENAI_API_KEY`** = your OpenAI key.
   - (`API_JWT_SECRET` is auto-generated; everything else has defaults.)
5. **Create / Deploy.** The build installs dependencies and runs the DB migration.

You'll get a live URL like **`https://hcm-lite-xxxx.onrender.com/`** (API docs at `/docs`).
Share that link with your teacher.

## First visit (and before you demo)

1. Open the URL. First load takes ~10–15s while embedded Qdrant initializes — normal.
2. The database starts empty, so the UI shows a **"Create admin"** screen. Enter your email /
   name / password — that becomes your login. No seeding needed.
3. Sign in → you're in the dashboard. From the admin account you can add more users
   (employee / manager) to show the role-based views.
4. **To demo the assistant's policy Q&A**, index the HR documents once. Open the service's
   **Shell** tab in Render and run:
   ```bash
   python -m hcm_lite.rag.ingest ingest
   ```

> **Tip for the showcase:** set the admin up (and run `ingest`) shortly before you present,
> and keep the tab open. If the service sleeps for ~15 min, the local data resets and you'd
> recreate the admin. For a live walkthrough that's a non-issue.

## If your teacher will open the link later on their own (optional, still free)

To keep the data between sleeps, point the app at free hosted databases instead of the local
files (your repo already supports both — see `.env.example`):

1. **Postgres** — create a free DB at **Neon** (neon.tech). Add a Render env var
   `DATABASE_URL` = `postgresql+asyncpg://USER:PASS@HOST/DBNAME` (drop any `?sslmode=...`).
2. **Qdrant** — create a free cluster at **Qdrant Cloud** (cloud.qdrant.io). Add Render env
   vars `VECTOR_STORE_URL` and `VECTOR_STORE_API_KEY`.

Redeploy, create the admin once, run `ingest` once — now it survives sleeps and redeploys.

## Troubleshooting

| Symptom | Fix |
|---|---|
| UI blank/slow on first load | first boot inits Qdrant (~10–15s); wait then reload |
| Missing key error at startup | set `OPENAI_API_KEY` in the Render dashboard |
| Assistant finds no policies | run `python -m hcm_lite.rag.ingest ingest` in the Render Shell |
| Data gone after a while | expected on free (it slept); recreate the admin, or use the persistent option above |
