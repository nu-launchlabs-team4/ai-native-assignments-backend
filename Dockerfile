FROM python:3.12-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The Claude Code CLI, for AI_PROVIDER=claude_code in local development only.
# docker-compose turns this on; CI and production images leave it out.
ARG INSTALL_CLAUDE_CODE=false
ARG CLAUDE_CODE_VERSION=2.1.330
RUN if [ "$INSTALL_CLAUDE_CODE" = "true" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends curl ca-certificates \
      && rm -rf /var/lib/apt/lists/* \
      && curl -fsSL https://claude.ai/install.sh | bash -s "$CLAUDE_CODE_VERSION"; \
    fi
ENV PATH="/root/.local/bin:${PATH}"

COPY pyproject.toml .
COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY tests ./tests

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
