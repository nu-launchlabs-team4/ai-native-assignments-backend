---
name: ai-feature
description: Rules for any code that calls the LLM (Anthropic API) or touches app/ai, such as the AI tutor chat, prompts, PDF-to-steps parsing, interview question generation and reasoning summaries. Use before writing or changing anything that builds a prompt, sends a request to the model, or handles a model reply.
---

# AI features

The AI is a tutor, not an answer machine, and it never judges honesty.

## Access rules for chat

- **Gate chat until step 1 is saved.** If the student has not saved their attempt (`Step.ATTEMPT`), return **403** with a clear message.
- **Close chat during the interview step** (`Step.EXPLAIN`). Chat requests during that step get 403.
- **Send only this student's work.** Include the assignment, this student's steps and this conversation. Never include other students' work.

## Prompts

- Prompts live in `app/ai/prompts/` as text files, not inline strings in Python.
- Pick the system prompt from the assignment's `HelpLevel`: `hints`, `approach` or `concepts`.

## Output rules

- **Never return full solutions.** Check every reply before returning it. If it contains a complete solution, such as a full function or the final answer to the task, rewrite it as a hint before sending it.
- **No cheating scores.** Never output a probability, percentage or label that says a student cheated or used AI. Reasoning summaries use `ReviewPriority` (`routine`, `worth_reviewing` or `needs_conversation`), always with specific reasons.
- **Log every message** (student and AI) as a `ChatMessage` row.

## Limits and config

- Apply `@limiter.limit(RATE_LIMIT_AI)` to every route that calls the model.
- Read the API key only from `get_settings().anthropic_api_key`. Never use `os.environ`, never hardcode it, and never log it.

## Tests

- **Always mock the LLM.** Tests must run without an API key or network access. Patch the client call in the service and return a fixed reply.
- Cover these cases:
  - chat before step 1 returns 403
  - chat during the interview step returns 403
  - a full-solution reply gets rewritten
  - messages get logged
