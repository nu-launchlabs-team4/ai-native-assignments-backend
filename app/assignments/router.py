import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.assignments import service
from app.assignments.schemas import AssignmentCreate, AssignmentOut, CourseCreate, CourseOut
from app.core.constants import Role
from app.core.database import get_db
from app.core.security import CurrentUser, require_role

router = APIRouter(prefix="/assignments", tags=["assignments"])
courses_router = APIRouter(prefix="/courses", tags=["courses"])

DbSession = Annotated[Session, Depends(get_db)]
Professor = Annotated[CurrentUser, Depends(require_role(Role.PROFESSOR))]


@courses_router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(body: CourseCreate, db: DbSession, professor: Professor) -> CourseOut:
    return service.create_course(db, professor, body)


@courses_router.get("", response_model=list[CourseOut])
def list_courses(db: DbSession, professor: Professor) -> list[CourseOut]:
    return service.list_courses(db, professor)


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
