---
name: new-endpoint
description: Checklist for adding or changing an API route in this FastAPI backend. Use when creating a new endpoint, changing a route's path, input, output, permissions or rate limit, or adding a router to a feature folder.
---

# Add or change an endpoint

Also follow the `clean-code` skill.

1. **Pick the feature folder:** `app/users`, `app/assignments`, `app/submissions`, `app/ai` or `app/sessions`. The router already has its prefix and tag and is included in `app/main.py`.

2. **Add schemas** in `schemas.py`: one for the request body and one for the response. Use the enums from `app/core/constants.py` for fixed values.

3. **Put the logic in `service.py`**, with a one-line docstring. The route only wires things together:
   ```python
   @router.post("", response_model=AssignmentOut, status_code=201)
   def create_assignment(
       body: AssignmentCreate,
       db: Annotated[Session, Depends(get_db)],
       user: Annotated[CurrentUser, Depends(require_role(Role.PROFESSOR))],
   ) -> AssignmentOut:
       return service.create_assignment(db, user, body)
   ```

4. **Check access:**
   - Use `require_role(Role.PROFESSOR)` or `require_role(Role.STUDENT)`, or `get_current_user` when any signed-in user is allowed.
   - In the service, also check ownership. Students see only their own work. Professors see only their own assignments.

5. **Apply a rate limit where needed.** The default (`RATE_LIMIT_DEFAULT`) applies to every route. For AI routes and PDF uploads, add the specific limit. The route must take `request: Request`:
   ```python
   from app.core.constants import RATE_LIMIT_AI
   from app.core.rate_limit import limiter

   @router.post("/chat")
   @limiter.limit(RATE_LIMIT_AI)
   def chat(request: Request, ...) -> ChatOut: ...
   ```

6. **Write tests** in `tests/`, at least:
   - the happy path, with the correct status and response body
   - one failure: wrong role (403), missing token (401), not found (404) or invalid input (422)

   Mock the database through `app.dependency_overrides[get_db]`, as `tests/conftest.py` does, and mock any LLM call. Error responses have the shape `{"error": {"code", "message", "request_id"}}`.

7. **Check `/docs`:** run `docker compose up -d` and open http://localhost:8010/docs. Confirm the route is listed under its feature tag with the right schemas.

8. Run ruff and pytest (see the `git-workflow` skill) before pushing.
