# Deployment Guide

Assembly is designed to be deployed as a decoupled application:
- **Frontend**: Vercel (Next.js App Router)
- **Backend**: Render (FastAPI Docker Container)
- **Database / Auth**: Supabase (PostgreSQL + Supabase Auth)

## 1. Environment Variables

Both the frontend and backend require specific environment variables to function correctly.

### Backend (`.env`)

| Variable | Purpose | Example | Secret? |
|----------|---------|---------|---------|
| `APP_ENV` | Sets the application environment. Use `production` for JSON logging. | `production` | No |
| `APP_MODE` | Determines how keys are handled. Must be `web` for public deployment to enforce BYOK. | `web` | No |
| `FRONTEND_URL` | Used for CORS and WebSocket origin verification. | `https://assembly.vercel.app` | No |
| `DATABASE_URL` | Supabase Postgres connection string. | `postgresql://postgres:[PASSWORD]@db.xxxx.supabase.co:5432/postgres` | **Yes** |
| `JWT_SECRET_KEY` | Must match your Supabase project's JWT secret for auth verification. | `your-supabase-jwt-secret` | **Yes** |
| `TAVILY_API_KEY` | Used for web research searches globally. | `tvly-...` | **Yes** |

### Frontend (`.env.local` / Vercel Environment Variables)

| Variable | Purpose | Example | Secret? |
|----------|---------|---------|---------|
| `NEXT_PUBLIC_APP_MODE` | Signals the UI to enforce BYOK and use Supabase Auth. | `web` | No |
| `NEXT_PUBLIC_API_URL` | Points to the Render backend API. | `https://assembly-api.onrender.com/api` | No |
| `NEXT_PUBLIC_SUPABASE_URL` | URL of your Supabase instance. | `https://xxxx.supabase.co` | No |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key for public API interactions. | `eyJhb...` | No |

## 2. Infrastructure Setup

### Supabase (Database & Auth)
1. Create a new project in Supabase.
2. Under **Authentication**, enable Email/Password (or Google OAuth if preferred).
3. Under **SQL Editor**, run the generated Alembic migrations to set up the `conversations` and `executions` tables.
4. Copy the `DATABASE_URL` (ensure it starts with `postgresql://`), `JWT Secret`, `URL`, and `Anon Key` for the next steps.

### Backend Deployment (Render)
Render is an excellent long-running host for FastAPI that supports WebSockets natively.

1. Create a new **Web Service** on Render connected to your GitHub repository.
2. Select **Docker** as the environment (Render will automatically detect the provided `Dockerfile`).
3. Set the Build Command and Start Command to empty (Docker handles this).
4. Add the **Backend Environment Variables** listed above.
5. Deploy.
6. **Free Tier Note**: Render free tiers spin down after 15 minutes of inactivity. Assembly implements a "wakeup" call on the frontend setup page to mitigate slow initial starts, but for guaranteed zero-delay debate rounds, a paid "Hobby" tier is recommended.

### Frontend Deployment (Vercel)
1. Create a new project on Vercel and import your repository.
2. Set the **Framework Preset** to Next.js.
3. Set the **Root Directory** to `frontend/app`.
4. Add the **Frontend Environment Variables** listed above.
5. Deploy.

## 3. Deployment Security & Scaling
- **Rate Limits**: The backend is pre-configured with IP-based and User-based rate limits (e.g., 5 executions / 60 seconds).
- **Concurrent Executions**: By default, each user is capped at 1 active concurrent execution to prevent abuse.
- **BYOK**: By setting `APP_MODE=web`, you guarantee that no server-side LLM API keys are ever used. Users must supply their own keys via the frontend, which are held entirely ephemerally in `RequestKeyStore` and wiped immediately after the request finishes.

## 4. Rollback Procedure

If a deployment introduces a critical bug, follow this rollback procedure:

**Frontend (Vercel)**
1. Navigate to your project on the Vercel Dashboard.
2. Click on the **Deployments** tab.
3. Find the last known stable deployment.
4. Click the three dots (`...`) and select **Promote to Production** (or **Redeploy**).

**Backend (Render)**
1. Navigate to your Web Service on the Render Dashboard.
2. Go to the **Events** tab.
3. Find the last successful deploy event.
4. Click **Deploy this commit**. 
5. If the rollback involves a database migration, you must manually run `alembic downgrade -1` via the Render Shell before rolling back the application code.

**Monitoring**
Monitor the deployment through Render's logs. In `production` mode, Assembly emits structured JSON logs which can be ingested by Datadog, Logtail, or AWS CloudWatch.
