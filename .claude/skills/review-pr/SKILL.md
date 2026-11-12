---
name: review-pr
description: Checklist for reviewing a teammate's pull request in this repo. Use when asked to review a PR, look over a branch or diff before merge, or leave review comments.
---

# Review a pull request

Get the context first:
```bash
gh pr view <N>
gh pr diff <N>
gh pr checks <N>
```

## Checklist

- [ ] **Matches the linked issue.** The PR has `Closes #N`, and it meets the issue's acceptance criteria with no unrelated changes. It aims for under 400 changed lines.
- [ ] **CI is green.** The `test` check passes: ruff check, ruff format and pytest.
- [ ] **Has tests.** Every new or changed route has a happy-path test and at least one failure test. The database and LLM are mocked.
- [ ] **Follows the clean-code rules:**
  - thin routes with logic in `service.py`
  - Pydantic schemas in and out
  - type hints
  - constants and settings from `app/core`
  - no `print`
  - no dead code
- [ ] **No secrets.** No `.env` file, keys, tokens, passwords or connection strings in the diff, tests or fixtures.
- [ ] **Routes check roles.** Routes use `require_role` or `get_current_user`, and services check ownership: students see only their own work, professors only their own assignments.
- [ ] **AI rules are followed** if `app/ai` changed or the LLM is called:
  - chat is gated until step 1 is saved and closed during the interview
  - the model gets only this student's work
  - no full solutions, and no cheating scores
  - every message is logged
  - `RATE_LIMIT_AI` is applied

## Comments

Be kind and specific, and suggest a fix:

> Good: "This query runs inside the route. Could it move to `service.get_submission` so the route stays thin? Something like `return service.get_submission(db, user, submission_id)`."

> Bad: "Wrong. Fix this."

Approve when the checklist passes. Request changes only for real problems, such as bugs, security issues, missing tests or broken rules, not for personal style.
