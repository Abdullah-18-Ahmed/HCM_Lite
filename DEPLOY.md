# Deploying HCM Lite — free + persistent (keeps working)

HCM Lite is a **FastAPI backend + single-page UI**, so it needs a host that runs Python
(not GitHub Pages / Vercel). This deploys it on **Render's free plan** and keeps all data by
pointing it at two **free** hosted databases, so the live link keeps working for your teacher:

- **Neon** — free Postgres (replaces the local SQLite file)
- **Qdrant Cloud** — free vector DB (replaces the embedded Qdrant folder)

The web service is then stateless: even though the free plan sleeps when idle (and takes
~30–60s to wake), your admin account, users, records, and the RAG index all survive restarts
and redeploys. Nothing resets.

> All free, no credit card: Render, Neon, and Qdrant Cloud all have no-card free tiers.

---

## Step 1 — Create the Postgres database (Neon)

1. Go to <https://neon.tech> → sign up → **New Project**.
2. Open **Connection string** / **Connect** and copy the URL. It looks like:
   `postgresql://user:pass@ep-xxx.region.aws.neon.tech/dbname?sslmode=require`
3. **Rewrite it for this app** — change the scheme to the async driver and drop the
   `?sslmode=...` part:
   ```
   postgresql+asyncpg://user:pass@ep-xxx.region.aws.neon.tech/dbname
   ```
   Keep this as **`DATABASE_URL`**.

## Step 2 — Create the vector database (Qdrant Cloud)

1. Go to <https://cloud.qdrant.io> → sign up → **Create cluster** (free tier).
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

You'll get a live URL like **`https://hcm-lite-xxxx.onrender.com/`** — share this with your
teacher (API docs at `/docs`).

## Step 4 — Use the app's real onboarding flow (it then persists)

No demo data / seed — you create real accounts through the app itself, and because the data
lives in Neon + Qdrant it all stays put.

1. Open the URL (first load ~10–15s while it connects to Qdrant — normal).
2. The database is empty, so the UI shows a **"Create admin"** screen (first-run setup).
   Enter your email / name / password — this becomes the **admin** account.
3. Sign in as the admin, then use the in-app **user management** to create accounts:
   - Admin can create **HR** and **employee** users.
   - HR can create **employee** users.
   - Each user signs in with the credentials you set and can **change their own password**.
4. **(Optional, for the AI assistant's policy Q&A)** Index the HR documents once — open the
   service's **Shell** tab in Render and run:
   ```bash
   python -m hcm_lite.rag.ingest ingest
   ```

That's it — the live link keeps working with the real accounts and data every time it's
opened. The full application functionality is unchanged from local.

---

## Notes & limits

- **Free plan sleeps** after ~15 min idle; the first request after that takes ~30–60s to
  wake. Your data is safe — only the compute sleeps.
- **Neon free tier** also auto-suspends the DB when idle and wakes on the first query (adds a
  second or two).
- To stop sleeping entirely, upgrade the Render service to a paid plan later — no code change.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails connecting to DB | `DATABASE_URL` must start with `postgresql+asyncpg://` (not `postgres://`) and have no `?sslmode=` suffix |
| `relation ... does not exist` | the migration didn't run; check the deploy log for `alembic upgrade head` |
| Assistant finds no policies | run `python -m hcm_lite.rag.ingest ingest` in the Render Shell |
| Qdrant auth error | re-check `VECTOR_STORE_URL` and `VECTOR_STORE_API_KEY` |
| Locked out of admin | the setup screen only appears while no admin exists; create users/roles from inside the app instead |
