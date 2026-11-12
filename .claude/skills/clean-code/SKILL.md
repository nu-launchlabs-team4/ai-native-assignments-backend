---
name: clean-code
description: Code style and structure rules for this FastAPI backend. Use whenever writing, changing or refactoring any Python file in this repo (app/ or tests/), including routes, services, schemas, models and tests.
---

# Clean code rules

Ruff must pass:
```bash
docker compose run --rm api ruff check .
docker compose run --rm api ruff format --check .
```

## Feature folders

Code lives in a feature folder: `app/users`, `app/assignments`, `app/submissions`, `app/ai` or `app/sessions`. Each has:
- `router.py`: routes only
- `schemas.py`: Pydantic models
- `service.py`: logic
- `models.py`: SQLAlchemy models

Shared code lives in `app/core`.

## Routes stay thin

The route parses input, checks access and calls the service. Logic goes in `service.py`.

```python
# Good
@router.post("", response_model=AssignmentOut)
def create_assignment(
    body: AssignmentCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role(Role.PROFESSOR))],
) -> AssignmentOut:
    return service.create_assignment(db, user, body)

# Bad: queries and rules inside the route
@router.post("")
def create_assignment(body: dict, db: Session = Depends(get_db)):
    if db.query(Assignment).filter_by(title=body["title"]).first(): ...
```

## Pydantic schemas in and out

```python
# Good
def get_submission(...) -> SubmissionOut: ...

# Bad: raw dicts and ORM objects leak fields and skip validation
def get_submission(...) -> dict: ...
```

## Type hints everywhere

```python
# Good
def count_steps(submission: Submission) -> int: ...

# Bad
def count_steps(submission): ...
```

## Small functions that do one thing

```python
# Good
def save_attempt(db: Session, submission: Submission, attempt: AttemptIn) -> StepEntry: ...
def notify_professor(submission: Submission) -> None: ...

# Bad
def save_attempt_and_notify_and_score(...): ...
```

## Clear names, no abbreviations

```python
# Good
submission_count = len(submissions)

# Bad
sub_cnt = len(subs)
```

## Constants and settings come from app/core

```python
# Good
from app.core.constants import MAX_PDF_MB, Role
from app.core.config import get_settings

if size_mb > MAX_PDF_MB: ...
api_key = get_settings().anthropic_api_key

# Bad: magic numbers, string literals and direct env access
if size_mb > 10: ...
if user.role == "professor": ...
api_key = os.environ["ANTHROPIC_API_KEY"]
```

## Errors: raise HTTPException and let the global handler format it

```python
# Good
raise HTTPException(status_code=404, detail="Assignment not found")

# Bad: hand-built error JSON skips the standard {"error": {...}} shape and the request_id
return JSONResponse(status_code=404, content={"msg": "nope"})
```

## Logging

Use the standard logger. Never `print`. Never log request bodies, tokens, passwords or `.env` values.

```python
# Good
logger = logging.getLogger(__name__)
logger.info("Submission saved submission_id=%s", submission.id)

# Bad
print(request_body)
logger.info("Login with token %s", token)
```

## No dead code

Delete unused code and commented-out code. Git keeps the history.

```python
# Bad
# def old_parser(text): ...
```

## Comments

Comment **why**, not what.

```python
# Good
# Supabase pauses idle connections, so pre-ping before reuse.
engine = create_engine(url, pool_pre_ping=True)

# Bad
# create the engine
engine = create_engine(url, pool_pre_ping=True)
```

Every public function in `service.py` gets a one-line docstring.

```python
# Good
def publish_assignment(db: Session, assignment_id: int) -> AssignmentOut:
    """Mark an assignment as published so students can see it."""

# Bad: no docstring on a public service function
def publish_assignment(db: Session, assignment_id: int) -> AssignmentOut: ...
```

For planned work, use `TODO(name):` with an issue number.

```python
# Good
# TODO(miaowen): verify the Supabase JWT signature (#4)

# Bad
# TODO fix later
```
