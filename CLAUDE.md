# CLAUDE.md

## Project

Backend API for **AI-Native Assignments**. Professors turn programming assignments into a five-step flow: attempt, feedback, evaluate, revise, explain. Students work through the steps with an AI tutor that helps without giving away the answer. Professors then review each student's reasoning trail.

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2, psycopg 3, pydantic-settings, slowapi
- Supabase Postgres through the Session pooler (no local database) and Supabase Auth
- Docker Compose. The API is on host port **8010**, because 8000 is used by another project.
- pytest for tests, ruff for linting and formatting

## Layout

```
app/
  core/
    config.py       Settings (pydantic-settings, from .env) and get_settings()
    constants.py    Enums and fixed values shared across features
    database.py     engine, SessionLocal, Base, get_db
    security.py     get_current_user, require_role(role)
    rate_limit.py   slowapi Limiter
    middleware.py   request ID, request logging, exception handlers
  users/            users and auth
  assignments/      courses and assignments
  submissions/      submissions and step entries
  ai/               AI tutor chat and generation
  sessions/         work sessions and activity events
  main.py           builds the app, adds middleware, includes routers, /health
tests/
```

Each feature folder has:
- `router.py`: an APIRouter with a prefix and tag
- `schemas.py`: Pydantic models
- `service.py`: the logic
- `models.py`: SQLAlchemy models, which subclass `app.core.database.Base`

A feature owns its own models.

## Settings and constants

- Settings live in `app/core/config.py`. Read them with `get_settings()`, never `os.environ`. Every new setting also goes in `.env.example` with a placeholder value.
- Shared fixed values live in `app/core/constants.py`:
  - Enums: Step, AIPolicy, HelpLevel, FinalCheck, ReviewPriority, Role
  - Values: `MAX_PDF_MB` and the rate limits

  Use these instead of string literals.

## Middleware and rate limits

- **Request ID:** reuses the incoming `X-Request-ID` or creates one, and returns it on every response.
- **Logging:** logs the method, path, status and duration in ms. It never logs request or response bodies, query strings or secrets.
- **Errors:** every error response has the shape `{"error": {"code", "message", "request_id"}}`. This covers HTTP errors, validation errors (422), rate limits (429) and unhandled errors (500). A 500 response never includes a stack trace.
- **Rate limits:** slowapi keys on the user id when the request is authenticated, else on the client IP.
  - The default limit is `RATE_LIMIT_DEFAULT` (60/minute).
  - Use `@limiter.limit(RATE_LIMIT_AI)` on AI routes and `@limiter.limit(RATE_LIMIT_PDF_UPLOAD)` on PDF upload. A route with `@limiter.limit` must take `request: Request`.
- **Auth:** `get_current_user` returns 401 when there's no bearer token. Supabase JWT verification is still a TODO, so for now it returns 501 for any token. Protect routes with `Depends(get_current_user)` or `Depends(require_role(Role.PROFESSOR))`.

## Commands

```bash
docker compose up --build -d                  # API on http://localhost:8010
docker compose run --rm api ruff check . --fix
docker compose run --rm api ruff format .
docker compose run --rm api pytest
```

## Rules

- Routes stay thin. Logic goes in `service.py`.
- Use Pydantic schemas for request and response bodies. Don't return ORM objects or raw dicts from feature routes.
- Use type hints everywhere.
- Every route gets a test. Mock the database and the LLM so tests run without Supabase or API keys.
- Never commit secrets, and never print, cat or log `.env`. This repo is public.
- The AI never returns full solutions, and it never produces cheating scores. Review priority is always `routine`, `worth_reviewing` or `needs_conversation`, with reasons.
- Keep PRs small, with one feature each.
- Branch names follow `type/issue-number-short-name`, where `type` is `feature`, `fix`, `chore` or `docs`. For example, `feature/10-ai-chat`. Never commit to `main`. See the `git-workflow` skill.

## Skills

Team skills live in `.claude/skills/`. Use the one that matches the task.

| Skill | When it applies |
|---|---|
| `setup-project` | A teammate is setting up the backend for the first time, or local setup breaks (port busy, "Field required", 503 from /health). |
| `clean-code` | Writing or changing any Python in this repo. |
| `git-workflow` | Creating a branch, committing, or opening or merging a PR. |
| `new-endpoint` | Adding or changing an API route. |
| `ai-feature` | Any code that calls the LLM or touches `app/ai`. |
| `review-pr` | Reviewing a teammate's pull request. |
| `ship-pr` | Only when someone types `/ship-pr`. It checks, commits, pushes and opens the PR. |
