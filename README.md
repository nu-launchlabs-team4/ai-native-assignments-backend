# AI-Native Assignments API

[![CI](https://github.com/nu-launchlabs-team4/ai-native-assignments-backend/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/nu-launchlabs-team4/ai-native-assignments-backend/actions/workflows/ci.yml)

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

## Contributing

1. Pick an issue from the Team 4 Sprint Board.
2. Branch from an up-to-date `main`, using the name `type/issue-number-short-name`, where `type` is `feature`, `fix`, `chore` or `docs`:
   ```bash
   git checkout main && git pull
   git checkout -b feature/10-ai-chat
   ```
3. Make the change, then run lint and tests (see above).
4. Open a PR with `Closes #N`. CI (the `test` check) must pass, and one approval is required before you squash merge.

Never commit `.env` or any secret. This repo is public.

### Claude Code skills

If you use Claude Code, the team skills in [`.claude/skills/`](.claude/skills/) load automatically:

| Skill | Use it for |
|---|---|
| `setup-project` | First-time setup and fixing a broken local setup |
| `clean-code` | Code style for any Python change |
| `git-workflow` | Branches, commits and PRs |
| `new-endpoint` | Adding or changing a route |
| `ai-feature` | Anything that calls the LLM or touches `app/ai` |
| `review-pr` | Reviewing a teammate's PR |
| `ship-pr` | Type `/ship-pr` to check, commit, push and open the PR |

Project conventions are in [CLAUDE.md](CLAUDE.md).
