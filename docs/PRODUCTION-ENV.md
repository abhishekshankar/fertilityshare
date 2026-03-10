# Production environment setup

Backend: **Railway**. Frontend: **Vercel**. PRD §10.1.

Use your real production URLs (e.g. `https://fertilityshare-api.up.railway.app`, `https://fertilityshare.vercel.app` or your custom domain) when setting these.

---

## 1. Railway (backend)

In [Railway](https://railway.app) → your project → backend service → **Variables**:

| Variable | Value | Notes |
|----------|--------|--------|
| `OPENAI_API_KEY` | `sk-...` | Required for pipeline. |
| `DATABASE_URL` | *(auto)* | Injected by Railway when you add Postgres. Use `postgresql://` (sync) for Alembic; app uses `postgresql+asyncpg://` (Railway usually provides one URL). |
| `JWT_SECRET` | *(random)* | Generate: `openssl rand -hex 32`. **Never** use the default from .env.example. |
| `GOOGLE_CLIENT_ID` | From Google Cloud Console | Required for Google OAuth. |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console | Required for Google OAuth. |
| `FRONTEND_URL` | `https://your-app.vercel.app` | Your Vercel app URL (or custom domain). Used for OAuth redirect after login. |
| `API_URL` | `https://your-backend.up.railway.app` | **Public** URL of this Railway service. Used to build the Google OAuth callback URL. |
| `ALLOWED_ORIGINS` | `https://your-app.vercel.app` | Comma-separated; must include your frontend origin for CORS. |
| `RATE_LIMIT_DEFAULT` | `100/minute` | Optional; default from .env.example. |
| `RATE_LIMIT_TRUST_PROXY` | `1` | Set to `1` when behind Railway’s proxy so rate limiting uses `X-Forwarded-For`. |
| `ALLOWED_EMAILS` | `beta@example.com,...` | Optional; comma-separated invite list. |

Optional (RAG, models): `RAG_INDEX_PATH`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_MODEL_*` — see `.env.example`.

### 1.1 Railway build & deploy (spec)

Railway builds the backend from repo code. Two supported paths:

| Path | When used | Behavior |
|------|-----------|----------|
| **Nixpacks** | No `Dockerfile` in project root (or Nixpacks selected in Railway) | Uses `nixpacks.toml` + `Procfile`. |
| **Docker** | `Dockerfile` present in project root | Builds image; runs `docker-entrypoint.sh` then `uvicorn` (see `Dockerfile` `CMD`). |

**Nixpacks + Procfile (default):**

- **`nixpacks.toml`** — Python 3.11, system pkgs `gcc` and `postgresql` (for psycopg2/libpq), install: `pip install .`.
- **`Procfile`**  
  - `release`: `alembic upgrade head` — runs before each deploy (Railway release phase).  
  - `web`: `uvicorn syllabus.api.main:app --host 0.0.0.0 --port $PORT` — Railway sets `$PORT`.

**Branch & CI:**

- **Railway** — In the service settings, set the **production branch** (e.g. `main` or `feat/v1-mvp`). Pushes to that branch trigger a build and deploy.
- **GitHub Actions** — `.github/workflows/deploy.yml` runs on push to `main`: deploys backend via `railway up` (requires `RAILWAY_TOKEN`, `RAILWAY_SERVICE_ID` in repo secrets) and frontend to Vercel. Keep the branch used by Railway in sync with the branch that triggers this workflow if you want one source of truth (e.g. both `main`).

---

## 2. Vercel (frontend)

In [Vercel](https://vercel.com) → your project → **Settings** → **Environment Variables** (Production):

| Variable | Value |
|----------|--------|
| `NEXT_PUBLIC_API_URL` | `https://your-backend.up.railway.app` |

Redeploy the frontend after changing env vars so the build picks them up.

---

## 3. Google OAuth — production callback URL

The backend uses **backend-hosted** OAuth: Google redirects to the **API**, not the frontend. Callback path: `/v1/auth/google/callback`.

**Production callback URL to add in Google Cloud Console:**

```
https://<API_URL>/v1/auth/google/callback
```

Replace `<API_URL>` with your **actual** Railway public URL (no trailing slash). Example:

```
https://fertilityshare-api.up.railway.app/v1/auth/google/callback
```

**Steps:**

1. Open [Google Cloud Console](https://console.cloud.google.com/) → your project → **APIs & Services** → **Credentials**.
2. Edit your **OAuth 2.0 Client ID** (Web application).
3. Under **Authorized redirect URIs**, add:
   - `https://your-backend.up.railway.app/v1/auth/google/callback`
   - (Keep `http://127.0.0.1:8000/v1/auth/google/callback` for local dev if you use it.)
4. Under **Authorized JavaScript origins** (if required), add:
   - `https://your-app.vercel.app`
   - Your Railway API URL if the consent screen is shown from the API origin.
5. Save.

After saving, OAuth redirects from production will work only if `API_URL` in Railway matches the host in the redirect URI exactly (same protocol and host).

---

## Quick checklist

- [ ] Railway: `OPENAI_API_KEY`, `JWT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `FRONTEND_URL`, `API_URL`, `ALLOWED_ORIGINS` set.
- [ ] Railway: Postgres added (so `DATABASE_URL` is set).
- [ ] Vercel: `NEXT_PUBLIC_API_URL` set to Railway backend URL.
- [ ] Google Cloud: Production redirect URI `https://<API_URL>/v1/auth/google/callback` added.
- [ ] Redeploy frontend after Vercel env changes.
