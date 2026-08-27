## Assembly — Deployment Audit & Migration Plan

> **Last updated**: 2026-08-27  
> **Goal**: Migrate from local SQLite to **Supabase PostgreSQL**, deploy backend on **Render**, deploy frontend on **Vercel**.

---

### 1. Current State of the Codebase

| Area | Status | Notes |
|---|---|---|
| Database layer (`src/database/base.py`) | ✅ Ready | Auto-detects `DATABASE_URL` — uses PostgreSQL when set, falls back to SQLite locally. Includes SSL and connection pooling. |
| PostgreSQL driver (`psycopg2-binary`) | ✅ Installed | Already in `requirements.txt` |
| CORS lockdown | ✅ Implemented | Restricts to `FRONTEND_URL` in production, allows `*` in dev |
| Static file separation | ✅ Done | Frontend lives in `/frontend`. `src/static` has been deleted. |
| WebSocket URL injection | ✅ Done | `app.js` properly derives WS URL from `window.ASSEMBLY_API_URL` for production. |
| Render configuration | ✅ Done | `Procfile` uses robust `gunicorn` + `uvicorn` workers. `render.yaml` defines environment, health check, and build commands. `runtime.txt` pins Python 3.11.9. |
| Vercel configuration | ✅ Done | `frontend/vercel.json` includes SPA rewrite rules, cache headers, and security headers. |
| Health check endpoint | ✅ `/health` | Tests actual database connectivity (`SELECT 1`) |

---

### 2. What Has Already Been Fixed

1. **Static File Conflict** — Separated frontend into standalone `frontend/` dir; `main.py` disables static serving when `FRONTEND_URL` is set. Old `src/static/` directory deleted.
2. **WebSocket Protocol Mismatch** — `app.js` now uses `window.ASSEMBLY_API_URL` to derive both REST and `wss://` endpoints correctly for production.
3. **Render Port Binding & Server** — Switched to `gunicorn` with `uvicorn` workers for a robust production server setup.
4. **CORS Security** — Dynamic CORS restricts access to `FRONTEND_URL` in production.
5. **Database Dual-Mode** — `base.py` supports both SQLite (local) and PostgreSQL (Supabase) with connection pooling and SSL mode enforced for Supabase. Health check verifies DB connectivity.
6. **Configuration** — `.env.example` has been updated to be the single source of truth for all required variables. `.gitignore` updated to exclude OS files and deprecated directories.

---

### 3. Supabase DB Migration — Action Checklist

- [ ] **Create Supabase project** at [supabase.com](https://supabase.com)
- [ ] **Copy the connection string** from **Project Settings → Database → Connection String (URI)**
  - Use **connection pooling** (port `6543`) with `?sslmode=require` appended
  - Ensure protocol is `postgresql://` (not `postgres://` — SQLAlchemy requires it, though the app will auto-fix it if necessary)
- [ ] **Set `DATABASE_URL`** in Render environment variables:
  ```
  postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require
  ```
- [ ] **Test locally** by setting `DATABASE_URL` in `.env` and running the app — tables should auto-create via `init_db()`
- [ ] **Verify tables** in Supabase Dashboard → Table Editor after first successful startup

> [!NOTE]
> The `assembly.db` SQLite file is local-only and gitignored. It will continue to work for local development — no changes needed.

---

### 4. Render (Backend) — Deployment Steps

1. **Create a new Web Service** on [render.com](https://render.com)
2. **Connect your GitHub repo** (branch: `main`)
3. **Configure settings** (or use the provided `render.yaml` Blueprints feature):

| Setting | Value |
|---|---|
| **Environment** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn src.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --graceful-timeout 30` |

4. **Set environment variables**:

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.11.9` |
| `APP_ENV` | `production` |
| `DEBUG` | `false` |
| `FRONTEND_URL` | `https://<your-vercel-app>.vercel.app` |
| `DATABASE_URL` | `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require` |
| `JWT_SECRET_KEY` | *(generate a 32+ char random string)* |
| `GEMINI_API_KEY` | *(your key)* |
| `GROQ_API_KEY` | *(your key, if used)* |
| `CEREBRAS_API_KEY` | *(your key, if used)* |
| `OPENROUTER_API_KEY` | *(your key, if used)* |
| `HUGGINGFACE_API_KEY`| *(your key, if used)* |
| `TAVILY_API_KEY`     | *(your key, if used)* |

5. **Deploy** and confirm `/health` returns `{"status": "healthy"}`

---

### 5. Vercel (Frontend) — Deployment Steps

1. **Create a new project** on [vercel.com](https://vercel.com)
2. **Connect your GitHub repo** (branch: `main`)
3. **Configure settings**:

| Setting | Value |
|---|---|
| **Framework Preset** | Other |
| **Root Directory** | `frontend` |
| **Build Command** | *(leave empty or `echo 'No build'`)* |
| **Output Directory** | `.` |

4. **Before deploying**, update `frontend/index.html`:
   ```javascript
   // ── Deploy-time Configuration ──────────────────────────────
   // LOCAL DEV:  Leave empty (same-origin, API served by FastAPI)
   // PRODUCTION: Set to your Render backend URL (no trailing slash)
   //   Example:  'https://assembly-backend.onrender.com'
   window.ASSEMBLY_API_URL = 'https://<your-render-app>.onrender.com';
   ```
5. **Deploy** and verify the frontend loads and connects to the backend

> [!TIP]
> To automate the backend URL injection, consider adding a Vercel environment variable (`VITE_API_URL` or similar) and a small pre-deploy script that rewrites the URL in `index.html`.

---

### 6. Files NOT Needed in Production

These files are workspace-only and should remain gitignored or excluded from deployment:

| File | Reason |
|---|---|
| `assembly.db` | Local SQLite DB — gitignored |
| `.env` | Secrets — never commit (use `.env.example` as a template) |
| `Assembly_PRD.docx` | Documentation only |
| `Assembly_Multi-Agent_AI_Consensus_Platform.md` | Documentation only |
| `audit.md` | Internal planning |
| `project.md` | Internal planning |
| `walkthrough.md` | Internal planning |

---

### 7. Post-Deployment Verification

- [ ] Hit `https://<render-app>.onrender.com/health` — should return `{"status": "healthy"}`
- [ ] Hit `https://<render-app>.onrender.com/docs` — Swagger UI should load
- [ ] Open `https://<vercel-app>.vercel.app` — frontend should load
- [ ] Register a new user → login → create a conversation → run an AI execution
- [ ] Verify data persists in Supabase Dashboard → Table Editor
- [ ] Check WebSocket connection works (real-time agent responses)
- [ ] Confirm CORS blocks requests from non-Vercel origins
