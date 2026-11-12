import logging
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.router import router as ai_router
from app.assignments.router import router as assignments_router
from app.core.config import get_settings
from app.core.database import get_db
from app.core.middleware import (
    REQUEST_ID_HEADER,
    LoggingMiddleware,
    RequestIDMiddleware,
    register_exception_handlers,
)
from app.core.rate_limit import limiter
from app.sessions.router import router as sessions_router
from app.submissions.router import router as submissions_router
from app.users.router import router as users_router

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(title="AI-Native Assignments API")
app.state.limiter = limiter

# The last middleware added runs first: CORS -> request ID -> logging -> rate limit.
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)

register_exception_handlers(app)

for router in (users_router, assignments_router, submissions_router, ai_router, sessions_router):
    app.include_router(router)


@app.get("/health", response_model=None)
def health(db: Annotated[Session, Depends(get_db)]) -> dict[str, str] | JSONResponse:
    try:
        db.execute(text("select 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "db": "unreachable"})
    return {"status": "ok", "db": "connected"}
