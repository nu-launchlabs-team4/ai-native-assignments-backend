import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.assignments import service
from app.assignments.schemas import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentUpdate,
    CourseCreate,
    CourseOut,
    EnrollmentOut,
    JoinCourseIn,
)
from app.core.constants import RATE_LIMIT_PDF_UPLOAD, Role
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import CurrentUser, require_role

router = APIRouter(prefix="/assignments", tags=["assignments"])
courses_router = APIRouter(prefix="/courses", tags=["courses"])

DbSession = Annotated[Session, Depends(get_db)]
Professor = Annotated[CurrentUser, Depends(require_role(Role.PROFESSOR))]
Student = Annotated[CurrentUser, Depends(require_role(Role.STUDENT))]


@courses_router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(body: CourseCreate, db: DbSession, professor: Professor) -> CourseOut:
    return service.create_course(db, professor, body)


@courses_router.get("", response_model=list[CourseOut])
def list_courses(db: DbSession, professor: Professor) -> list[CourseOut]:
    return service.list_courses(db, professor)


@courses_router.post("/join", response_model=EnrollmentOut)
def join_course(body: JoinCourseIn, db: DbSession, student: Student) -> EnrollmentOut:
    return service.join_course(db, student, body)


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(body: AssignmentCreate, db: DbSession, professor: Professor) -> AssignmentOut:
    return service.create_assignment(db, professor, body)


@router.get("", response_model=list[AssignmentOut])
def list_assignments(
    course_id: uuid.UUID, db: DbSession, professor: Professor
) -> list[AssignmentOut]:
    return service.list_assignments(db, professor, course_id)


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: uuid.UUID, db: DbSession, professor: Professor) -> AssignmentOut:
    return service.get_assignment(db, professor, assignment_id)


@router.patch("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    assignment_id: uuid.UUID, body: AssignmentUpdate, db: DbSession, professor: Professor
) -> AssignmentOut:
    return service.update_assignment(db, professor, assignment_id, body)


@router.post("/{assignment_id}/publish", response_model=AssignmentOut)
def publish_assignment(
    assignment_id: uuid.UUID, db: DbSession, professor: Professor
) -> AssignmentOut:
    return service.publish_assignment(db, professor, assignment_id)


@router.post("/{assignment_id}/pdf", response_model=AssignmentOut)
@limiter.limit(RATE_LIMIT_PDF_UPLOAD)
def upload_assignment_pdf(
    request: Request,
    assignment_id: uuid.UUID,
    file: UploadFile,
    db: DbSession,
    professor: Professor,
) -> AssignmentOut:
    return service.upload_assignment_pdf(db, professor, assignment_id, file.file)
