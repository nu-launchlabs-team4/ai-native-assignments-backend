---
name: setup-project
description: Set up the AI-Native Assignments backend on a new machine, or fix a broken local setup. Use when a teammate is cloning the repo for the first time, creating .env, running Docker Compose, or when /health fails, the container will not start, port 8010 is busy, or settings raise "Field required".
---

# Set up the backend

The API runs in Docker and talks to Supabase Postgres through the Session pooler. There is no local database. The API is on host port **8010**.

## Steps

1. **Install Docker Desktop** and start it. `docker info` should print server details.
2. **Clone the repo:**
   ```bash
   git clone https://github.com/nu-launchlabs-team4/ai-native-assignments-backend.git
   cd ai-native-assignments-backend
   ```
3. **Get the `.env` values from Akash privately**, by direct message and never in a public channel. Never commit them, paste them into issues or PRs, or print `.env`.
4. **Create `.env`:**
   ```bash
   cp .env.example .env
   ```
   Fill in `DATABASE_URL`, `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. `ANTHROPIC_API_KEY` is optional for now.
5. **Start the API:**
   ```bash
   docker compose up --build -d
   ```
6. **Check health:** open http://localhost:8010/health. You should see:
   ```json
   {"status": "ok", "db": "connected"}
   ```
7. **Run lint and tests inside the container:**
   ```bash
   docker compose run --rm api ruff check .
   docker compose run --rm api ruff format --check .
   docker compose run --rm api pytest
   ```

## Troubleshooting

Look at the logs first: `docker compose logs api`. Never paste the full logs or `.env` anywhere public.

| Symptom | Cause | Fix |
|---|---|---|
| `Bind for 0.0.0.0:8010 failed: port is already allocated` | Something else is using port 8010. | Find it with `lsof -nP -iTCP:8010 -sTCP:LISTEN` or `docker ps`. Stop it, or change the host port in `docker-compose.yml` for your machine only. Don't commit that change. |
| `ValidationError ... Field required` in the logs | `.env` is missing a setting. The error names the field but not its value. | Compare `.env` with `.env.example` and add the missing line. Save the file, then run `docker compose up -d --force-recreate`. |
| `ModuleNotFoundError: No module named 'psycopg2'` | `DATABASE_URL` starts with `postgresql://`. | Change the start to `postgresql+psycopg://`. Also make sure the password has no `[ ]` brackets, and percent-encode special characters such as `@`, `:`, `/` and `#`. |
| `/health` returns 503 `{"db": "unreachable"}` | Wrong host, user or password, or the Supabase project is paused. | Supabase pauses free projects after about a week with no activity. Open the Supabase dashboard and click **Restore project**, then wait for it to come up. If it isn't paused, recopy the Session pooler string, which uses port 5432 and a user like `postgres.<project-ref>`. |
| Container exits right away | Usually one of the problems above. | Check `docker compose logs api` and start from the first error line. |
