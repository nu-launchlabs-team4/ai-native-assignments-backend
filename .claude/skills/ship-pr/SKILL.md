---
name: ship-pr
description: Check, commit, push and open a pull request for the current branch. Runs only when someone types /ship-pr.
disable-model-invocation: true
---

# Ship a PR

Follow these steps in order. Stop and report if any step fails.

1. **Confirm you're not on main.**
   ```bash
   git branch --show-current
   ```
   If the branch is `main`, stop. Create a branch named after the `git-workflow` skill's rules first.

2. **Check for secrets.**
   ```bash
   git status --short
   ```
   - If `.env` appears as staged or untracked-to-be-added, stop.
   - Scan the diff (`git diff` and `git diff --cached`) for keys, tokens, passwords and connection strings. If you find any, stop and tell the user. Never print `.env`.

3. **Run lint and tests in Docker.**
   ```bash
   docker compose run --rm api ruff check .
   docker compose run --rm api ruff format --check .
   docker compose run --rm api pytest -q
   ```
   Fix any failures before continuing.

4. **Get the issue number.** If the branch name includes it (`feature/10-ai-chat` → `#10`), use that. Otherwise, ask the user for the issue number. Don't guess.

5. **Commit.** Stage the relevant files by name. Write a short, imperative message, such as "Add AI chat endpoint". Then run `git status` again to confirm `.env` is not staged.

6. **Push.**
   ```bash
   git push -u origin HEAD
   ```

7. **Open the PR** with the template's sections:
   ```bash
   gh pr create --base main --title "<commit-style title>" --body "$(cat <<'EOF'
   ## What changed

   ## Why

   ## How to test

   Closes #N
   EOF
   )"
   ```
   Fill in each section from the actual diff.

8. **Show the PR link** that `gh` printed.
