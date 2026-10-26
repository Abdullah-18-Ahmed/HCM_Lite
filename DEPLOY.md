# Deploying HCM Lite — free + persistent

HCM Lite is a **FastAPI backend + single-page UI**, so it needs a host that runs Python
(not GitHub Pages / Vercel). This guide deploys it on **Render's free plan** and keeps all
data by pointing it at two **free** hosted databases:

- **Neon** — free Postgres (replaces the local SQLite file)
- **Qdrant Cloud** — free vector DB (replaces the embedded Qdrant folder)

That way the web service is stateless: even though the free plan sleeps when idle, your admin
account, records, and the RAG index all survive restarts and redeploys.

> Everything below is free. You'll create 3 accounts (Render, Neon, Qdrant Cloud) with GitHub
> or email — no card required.

---

## Step 1 — Create the Postgres database (Neon)

1. Go to <https://neon.tech> → sign up → **New Project**.
2. Open **Connection string** / **Connect** and copy the connection URL. It looks like:
   `postgresql://user:pass@ep-xxx.region.aws.neon.tech/dbname?sslmode=require`
3. **Convert it for this app** — change the scheme to the async driver and drop the
   `?sslmode=...` query:
   ```
   postgresql+asyncpg://user:pass@ep-xxx.region.aws.neon.tech/dbname
   ```
   Keep this handy as **`DATABASE_URL`**.

## Step 2 — Create the vector database (Qdrant Cloud)

1. Go to <https://cloud.qdrant.io> → sign up → **Create cluster** (pick the free tier).
2. From the cluster page copy:
   - **Cluster URL** (e.g. `https://xxxx.aws.cloud.qdrant.io:6333`) → **`VECTOR_STORE_URL`**
   - **API key** → **`VECTOR_STORE_API_KEY`**

## Step 3 — Deploy on Render

1. Go to <https://dashboard.render.com> → sign in **with GitHub**.
2. **New +** → **Blueprint** → pick the **`HCM_Lite`** repo → **Apply**.
   Render reads `render.yaml` and creates the `hcm-lite` web service (free plan).
3. When prompted, fill in the values marked "set by hand":
   | Variable | Value |
   |---|---|
   | `OPENAI_API_KEY` | your OpenAI key |
   | `DATABASE_URL` | the `postgresql+asyncpg://...` URL from Step 1 |
   | `VECTOR_STORE_URL` | the Qdrant cluster URL from Step 2 |
   | `VECTOR_STORE_API_KEY` | the Qdrant API key from Step 2 |

   (`API_JWT_SECRET` is auto-generated; the rest have defaults.)
4. **Create / Deploy.** The build installs dependencies, then `alembic upgrade head` creates
   the schema in your Neon database.

You'll get a live URL like **`https://hcm-lite-xxxx.onrender.com/`** (API docs at `/docs`).

## Step 4 — First visit

1. Open the URL (first load ~10–15s while it connects to Qdrant — normal).
2. The database is empty, so the UI shows a **"Create admin"** screen. Enter your email /
   name / password — that becomes your login. (No seeding needed.)
3. To enable the assistant's policy Q&A, open the service's **Shell** tab in Render once and
   run:
   ```bash
   python -m hcm_lite.rag.ingest ingest
   ```

Because the data now lives in Neon + Qdrant, you only do Step 4 **once** — it persists.

---

## Notes & limits

- **Free plan sleeps** after ~15 min idle; the first request after that takes ~30–60s to
  wake. Your data is safe — only the compute sleeps.
- **Neon free tier** also auto-suspends the DB when idle; it wakes on the first query (adds a
  second or two). Fine for a demo.
- To stop sleeping entirely, upgrade the Render service to a paid plan later — no code change.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails: `ModuleNotFoundError: asyncpg` | it's in `requirements.txt`; trigger a clean redeploy |
| Deploy fails connecting to DB | check `DATABASE_URL` uses `postgresql+asyncpg://` (not `postgres://`) and has no `?sslmode=` suffix |
| `relation ... does not exist` | the migration didn't run; check the deploy log for `alembic upgrade head` |
| Assistant finds no policies | run `python -m hcm_lite.rag.ingest ingest` in the Render Shell |
| Qdrant auth error | re-check `VECTOR_STORE_URL` and `VECTOR_STORE_API_KEY` |
