# Hosted Deployment

> Status: **deprioritized after the desktop-first decision on April 3, 2026.**
>
> This document is kept for future hosted work and for local hosted-sandbox testing, but Launchboard's next major product milestone is the desktop app plan in [docs/desktop-first.md](desktop-first.md).

Launchboard now supports two operating modes:

- `local/self-host`: SQLite, local files, optional user-configured AI providers
- `hosted/public-beta`: Supabase Auth, Postgres, Supabase Storage, durable worker-backed search runs

## Recommended stack

- Frontend: Cloudflare Pages or Vercel
- API: Render web service running `uvicorn app.main:app`
- Worker: Render background worker running `python -m app.worker`
- Auth/DB/Storage: Supabase

## Backend env

Start from [backend/.env.example](../backend/.env.example).

Hosted mode needs:

```bash
HOSTED_MODE=true
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/launchboard
MANAGE_SCHEMA_ON_STARTUP=false

SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_STORAGE_BUCKET=launchboard-private
SUPABASE_JWT_AUDIENCE=authenticated

HOSTED_PLATFORM_MANAGED_AI=true
HOSTED_ALLOW_WORKSPACE_LLM_CONFIG=false
```

If your Supabase project still uses the legacy shared JWT secret, set `SUPABASE_JWT_SECRET`. Otherwise leave it blank and the backend will verify bearer tokens against the project JWKS endpoint.

## Frontend env

The frontend needs these build-time vars:

```bash
VITE_API_URL=https://api.yourdomain.com/api/v1
VITE_HOSTED_MODE=true
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=...
```

## Migrations

Hosted deployments should use Alembic, not runtime schema creation:

```bash
./.venv/bin/python -m alembic upgrade head
```

For local SQLite development, `MANAGE_SCHEMA_ON_STARTUP` can stay unset and the app will create tables automatically.

## Worker

Hosted search runs are queued in `workspace_search_runs` and executed by the worker process. The web service only enqueues runs and streams durable progress from the database.

Render worker command:

```bash
python -m app.worker
```

Health checks:

- API: `GET /health`
- worker status: `GET /health/worker`

## Supabase setup

- Enable Google as a social provider in Supabase Auth.
- Enable email magic links as fallback.
- Create a private storage bucket matching `SUPABASE_STORAGE_BUCKET`.
- Keep the `SUPABASE_SERVICE_ROLE_KEY` on the backend only.

## Hosted-like local test path

For integration testing against a hosted-style backend:

1. Point `DATABASE_URL` at a Postgres instance.
2. Set `HOSTED_MODE=true`.
3. Run `alembic upgrade head`.
4. Start the API and the worker separately.
5. Build the frontend with `VITE_HOSTED_MODE=true` and Supabase client env vars.

## Local hosted sandbox

For daily development, you do not need a real Supabase project just to exercise hosted-mode behavior.
Launchboard now has a local hosted sandbox that:

- uses bearer-authenticated hosted routes
- starts the durable worker
- starts with a blank test-account flow that mirrors the real upload-your-resume experience
- includes optional realistic sample personas with different resumes and search goals
- stores sandbox data separately under `data/dev-hosted`

Start it with:

```bash
make dev-hosted
```

Then open `http://localhost:5173` and sign in as one of the seeded personas from the auth screen.
The primary path is a blank test account that behaves like a new hosted user. Sample personas are available as an optional developer tool from the same auth screen.

Reset the sandbox database and files with:

```bash
make dev-hosted-reset
```

### Custom persona sets

To test your own user mix, point `DEV_HOSTED_PERSONAS_PATH` at a JSON array of personas before starting the sandbox:

```bash
export DEV_HOSTED_PERSONAS_PATH="$PWD/docs/dev-personas.example.json"
make dev-hosted
```

Each persona object supports:

- `id`, `email`, `full_name`
- `headline`, `background`, `job_search_focus`
- `current_title`, `current_level`
- `target_roles`, `keywords`
- `preferred_places`
- `workplace_preference`
- `compensation`
- `resume_filename`, `resume_text`

`preferred_places` uses the same shape as the onboarding API. See [docs/dev-personas.example.json](dev-personas.example.json) for a concrete example.
