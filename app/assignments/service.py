"""Business logic for assignments. Routes call these functions and stay thin."""

import logging
import uuid
from typing import BinaryIO

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments import storage
from app.assignments.models import Assignment, Course, Question
from app.assignments.schemas import AssignmentCreate, AssignmentOut, CourseCreate, CourseOut
from app.core.constants import MAX_PDF_MB
from app.core.security import CurrentUser

logger = logging.getLogger(__name__)

COURSE_NOT_FOUND = "Course not found"
ASSIGNMENT_NOT_FOUND = "Assignment not found"
PDF_TOO_LARGE = f"PDF must be {MAX_PDF_MB} MB or smaller"
NOT_A_PDF = "File must be a PDF"
PDF_STORAGE_FAILED = "Could not store the PDF. Try again later."

MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024
# Every PDF file starts with these bytes, whatever its name or claimed content type says.
PDF_SIGNATURE = b"%PDF-"


def create_course(db: Session, professor: CurrentUser, body: CourseCreate) -> CourseOut:
    """Create a course owned by this professor."""
    course = Course(title=body.title, professor_id=_user_uuid(professor))
    db.add(course)
    db.commit()
    db.refresh(course)
    logger.info("Course created course_id=%s", course.id)
    return CourseOut.model_validate(course)


def list_courses(db: Session, professor: CurrentUser) -> list[CourseOut]:
    """List this professor's courses, oldest first."""
    courses = db.scalars(
        select(Course)
        .where(Course.professor_id == _user_uuid(professor))
        .order_by(Course.created_at, Course.id)
    )
    return [CourseOut.model_validate(course) for course in courses]


def create_assignment(db: Session, professor: CurrentUser, body: AssignmentCreate) -> AssignmentOut:
    """Create an assignment and its questions in one of this professor's courses."""
    course = _get_owned_course(db, professor, body.course_id)
    assignment = Assignment(
        course_id=course.id,
        title=body.title,
        instructions=body.instructions,
        ai_policy=body.ai_policy,
        help_level=body.help_level,
        final_check=body.final_check,
        questions=[
            Question(
                position=position,
                prompt=question.prompt,
                answer_type=question.answer_type,
                language=question.language,
                starter_code=question.starter_code,
            )
            for position, question in enumerate(body.questions, start=1)
        ],
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    logger.info("Assignment created assignment_id=%s", assignment.id)
    return AssignmentOut.model_validate(assignment)


def list_assignments(
    db: Session, professor: CurrentUser, course_id: uuid.UUID
) -> list[AssignmentOut]:
    """List the assignments in one of this professor's courses, oldest first."""
    course = _get_owned_course(db, professor, course_id)
    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.course_id == course.id)
        .order_by(Assignment.created_at, Assignment.id)
    )
    return [AssignmentOut.model_validate(assignment) for assignment in assignments]


def get_assignment(db: Session, professor: CurrentUser, assignment_id: uuid.UUID) -> AssignmentOut:
    """Get one of this professor's assignments with its questions in order."""
    return AssignmentOut.model_validate(_get_owned_assignment(db, professor, assignment_id))


def upload_assignment_pdf(
    db: Session, professor: CurrentUser, assignment_id: uuid.UUID, file: BinaryIO
) -> AssignmentOut:
    """Store a PDF for one of this professor's assignments and record where it is."""
    assignment = _get_owned_assignment(db, professor, assignment_id)
    content = _read_pdf(file)

    # A new name per upload, so a replaced PDF never overwrites the old file mid-read.
    path = f"assignments/{assignment.id}/{uuid.uuid4()}.pdf"
    try:
        storage.upload_pdf(path, content)
    except storage.StorageError as error:
        logger.error("PDF upload failed assignment_id=%s reason=%s", assignment.id, error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=PDF_STORAGE_FAILED
        ) from error

    assignment.source_pdf = path
    db.commit()
    db.refresh(assignment)
    logger.info("Assignment PDF uploaded assignment_id=%s", assignment.id)
    return AssignmentOut.model_validate(assignment)


def _read_pdf(file: BinaryIO) -> bytes:
    # Read one byte past the limit, so an oversized file is caught without loading all of it.
    content = file.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=PDF_TOO_LARGE)
    if not content.startswith(PDF_SIGNATURE):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_A_PDF)
    return content


def _get_owned_assignment(
    db: Session, professor: CurrentUser, assignment_id: uuid.UUID
) -> Assignment:
    # Another professor's assignment is a 404, not a 403, so ids can't be probed.
    assignment = db.scalar(
        select(Assignment)
        .join(Course)
        .where(Assignment.id == assignment_id, Course.professor_id == _user_uuid(professor))
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ASSIGNMENT_NOT_FOUND)
    return assignment


def _get_owned_course(db: Session, professor: CurrentUser, course_id: uuid.UUID) -> Course:
    # Another professor's course is a 404, not a 403, so ids can't be probed.
    course = db.scalar(
        select(Course).where(Course.id == course_id, Course.professor_id == _user_uuid(professor))
    )
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=COURSE_NOT_FOUND)
    return course


def _user_uuid(user: CurrentUser) -> uuid.UUID:
    # Supabase Auth user ids are UUIDs; CurrentUser keeps them as strings.
    return uuid.UUID(user.id)
