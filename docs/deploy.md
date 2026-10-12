# Deployment Guide

Assembly has two persistence modes:

- **Hosted website:** stateless FastAPI backend; user history, settings, and keys are owned by the browser. The web backend does not use a database.
- **Local development / future Windows desktop app:** SQLite remains available for local backend history and metadata.

There is no PostgreSQL, Supabase Auth, account system, or server-side conversation database in the current web architecture.

## 1. Hosted architecture

- **Frontend:** Vercel, using the `frontend/` directory as the project root.
- **Backend:** Render, using the repository's `render.yaml` blueprint or the included `Dockerfile`.
- **Persistence:** none on the hosted backend. Do not configure `DATABASE_URL`, Supabase credentials, or JWT authentication secrets.

## 2. Backend deployment (Render)

The included `render.yaml` defines the web service. Configure these environment variables:

| Variable | Purpose |
|---|---|
| `APP_ENV` | Set to `production`. |
| `APP_MODE` | Set to `web` to enforce stateless BYOK runs. |
| `DEBUG` | Set to `false`. |
| `FRONTEND_URL` | The deployed frontend origin. |
| `CORS_ALLOW_LIST` | Comma-separated allowed frontend origins; production startup requires this value. |
| `QUOTA_SALT` | A random deployment-specific salt for quota-key fingerprints; Render's blueprint generates it. |
| `ALLOW_SERVER_SEARCH_KEY` | Keep `false`; web requests use per-request search keys by default. |

Users supply provider API keys through the browser for a run. Do not add users' provider keys to hosted environment variables. A server-side Tavily key is optional and is ignored by default in web mode unless `ALLOW_SERVER_SEARCH_KEY` is deliberately enabled.

Deploy the service, then verify its `/health` endpoint before connecting the frontend.

## 3. Frontend deployment (Vercel)

1. Import the repository in Vercel.
2. Set **Root Directory** to `frontend`.
3. Set the Framework Preset to Next.js.
4. Configure:
   - `NEXT_PUBLIC_API_URL`: the backend origin, with no trailing slash (for example, `https://your-backend.onrender.com`).
   - `NEXT_PUBLIC_APP_MODE`: `web`.
5. Deploy and test a full run with browser-supplied provider keys.

## 4. Data handling

In web mode, questions, provider keys, and intermediate execution state are processed in memory for the active request/run; there is no database write for user history. The server emits metadata-only operational logs. The browser stores history and settings in IndexedDB (with the app's documented fallback behavior). Browser data can be lost if site data is cleared, so use the Export/Import feature for portable backups.

External model and search providers receive the relevant request data under their own policies. Review the privacy notice before sending sensitive material.

## 5. Rollback

Use the Vercel or Render dashboard to promote/redeploy a previous working deployment. The stateless web release has no database migration or database rollback step.
