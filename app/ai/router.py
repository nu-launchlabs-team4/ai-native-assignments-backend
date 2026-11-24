"""API routes for AI tutoring chat."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.ai import service
from app.ai.schemas import ChatRequest, ChatResponse
from app.core.constants import RATE_LIMIT_AI, Role
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import CurrentUser, require_role

router = APIRouter(prefix="/ai", tags=["ai"])

DbSession = Annotated[Session, Depends(get_db)]
Student = Annotated[CurrentUser, Depends(require_role(Role.STUDENT))]


@router.post(
    "/submissions/{submission_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(RATE_LIMIT_AI)
def chat(
    request: Request,
    submission_id: uuid.UUID,
    body: ChatRequest,
    db: DbSession,
    student: Student,
) -> ChatResponse:
    """Send a message to the AI tutor for the student's submission."""
    saved_message = service.send_message(
        db=db,
        student=student,
        submission_id=submission_id,
        message=body.message,
    )
    return ChatResponse(
        message_id=saved_message.id,
        reply=saved_message.content,
    )
