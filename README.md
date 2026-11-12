# AI-Native Assignments API

Backend for the AI-Native Assignments project. Built with FastAPI and SQLAlchemy, it runs in Docker and uses a Supabase Postgres database through the Session pooler. You don't need a local Postgres.

## Prerequisites

- Docker Desktop, running
- Access to the team's Supabase project

## 1. Fill in `.env`

```bash
cp .env.example .env
```

In Supabase, open **Connect** and choose **Session pooler**. Copy the connection string into `DATABASE_URL` in `.env` and change it in two ways:

1. Change the scheme from `postgresql://` to `postgresql+psycopg://`.
2. Replace `[YOUR-PASSWORD]` with your database password, without the brackets.

```
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@<region>.pooler.supabase.com:5432/postgres
```

`.env` is gitignored. Never commit it.

## 2. Run with Docker

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

A healthy response is `{"status": "ok", "db": "connected"}`. If the API can't reach the database, it returns HTTP 503 with `{"status": "error", "db": "unreachable"}`.

`./app` and `./tests` are mounted into the container, so code changes reload automatically. To see logs, run `docker compose logs -f api`. To stop the API, run `docker compose down`.

Interactive API docs are at http://localhost:8000/docs.

## 3. Run tests

```bash
docker compose run --rm api pytest
```

The tests mock the database, so they don't need Supabase.

## Project layout

```
app/
  main.py         FastAPI app and /health route
  auth/           (empty packages, filled in by later features)
  assignments/
  submissions/
  ai/
  sessions/
  models/
tests/
  test_health.py
```
