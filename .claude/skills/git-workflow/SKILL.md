---
name: git-workflow
description: Team rules for branches, commits and pull requests in this repo. Use when creating a branch, naming a branch, writing a commit message, committing, pushing, or opening or merging a pull request.
---

# Git workflow

## Branches

Name branches `type/issue-number-short-name`, where `type` is one of `feature`, `fix`, `chore` or `docs`.

- `feature/10-ai-chat`
- `fix/27-health-timeout`
- `chore/3-backend-ci`

Never commit to `main`; it is protected. Always pull `main` before branching:

```bash
git checkout main && git pull
git checkout -b feature/10-ai-chat
```

## Commits

- Keep them short and use the imperative mood: "Add AI chat endpoint", "Fix 403 on missing attempt".
- Not: "added stuff", "fixes", "WIP".
- Make one logical change per commit.

## Pull requests

- One issue per PR. Aim for under 400 changed lines.
- Fill in the template: What changed, Why, How to test.
- Link the issue with `Closes #N`.
- Get one approval before merging.
- Squash merge, then delete the branch.

## Before pushing

```bash
docker compose run --rm api ruff check .
docker compose run --rm api ruff format --check .
docker compose run --rm api pytest
git status          # .env must not appear as staged
```

If `.env` or any secret is staged, unstage it (`git restore --staged .env`) and stop.
