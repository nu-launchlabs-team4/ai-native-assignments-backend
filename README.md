# AI-Native Assignments API

Backend for the AI-Native Assignments project. Built with FastAPI and SQLAlchemy, it runs in Docker and uses Supabase Postgres through the Session pooler. You don't need a local Postgres.

## Prerequisites

- Docker Desktop, running
- Access to the team's Supabase project

## 1. Fill in `.env`

```bash
cp .env.example .env
```

| Variable | Where to find it |
|---|---|
| `DATABASE_URL` | Supabase → **Connect** → **Session pooler**. Change `postgresql://` to `postgresql+psycopg://`, and replace `[YOUR-PASSWORD]` with your password, without the brackets. |
| `SUPABASE_URL` | Supabase → **Project Settings** → **API** → Project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase → **Project Settings** → **API Keys** → publishable key |
| `ANTHROPIC_API_KEY` | Optional for now |
| `ALLOWED_ORIGINS` | Comma-separated frontend origins. The default is `http://localhost:3000`. |
| `ENV` | `local` by default |

`.env` is gitignored. Never commit it.

## 2. Run with Docker

The API is on host port **8010**, so it doesn't clash with other projects that use 8000.

```bash
docker compose up --build -d
curl http://localhost:8010/health
```

A healthy response is `{"status": "ok", "db": "connected"}`. If the API can't reach the database, it returns HTTP 503 with `{"status": "error", "db": "unreachable"}`.

- API docs: http://localhost:8010/docs
- Logs: `docker compose logs -f api`
- Stop: `docker compose down`

`./app` and `./tests` are mounted into the container, so code changes reload automatically.

## 3. Lint and test

```bash
docker compose run --rm api ruff check . --fix
docker compose run --rm api ruff format .
docker compose run --rm api pytest
```

The tests mock the database, so they don't need Supabase.

## Project layout

```
app/
  core/            config, constants, database, security, rate limiting, middleware
  users/           users and auth
  assignments/     courses and assignments
  submissions/     submissions and step entries
  ai/              AI tutor
  sessions/        work sessions and activity events
  main.py          app setup and /health
tests/
```

Each feature folder has `router.py`, `schemas.py`, `service.py` and `models.py`. See [CLAUDE.md](CLAUDE.md) for conventions.
