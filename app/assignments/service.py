"""Business logic for assignments. Routes call these functions and stay thin."""

import logging
import uuid
from datetime import UTC, datetime
from typing import BinaryIO

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assignments import storage
from app.assignments.join_codes import new_join_code, normalize_join_code
from app.assignments.models import Assignment, Course, Enrollment, Question
from app.assignments.schemas import (
    AssignmentCreate,
    AssignmentFields,
    AssignmentOut,
    AssignmentUpdate,
    CourseCreate,
    CourseOut,
    EnrollmentOut,
    JoinCourseIn,
)
from app.core.constants import MAX_PDF_MB
from app.core.security import CurrentUser

logger = logging.getLogger(__name__)

COURSE_NOT_FOUND = "Course not found"
ASSIGNMENT_NOT_FOUND = "Assignment not found"
ALREADY_PUBLISHED = "This assignment is published, so it can't be changed"
UNKNOWN_JOIN_CODE = "No course has that code. Check it with your professor."
PDF_TOO_LARGE = f"PDF must be {MAX_PDF_MB} MB or smaller"
NOT_A_PDF = "File must be a PDF"
PDF_STORAGE_FAILED = "Could not store the PDF. Try again later."

MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024
# Every PDF file starts with these bytes, whatever its name or claimed content type says.
PDF_SIGNATURE = b"%PDF-"


def create_course(db: Session, professor: CurrentUser, body: CourseCreate) -> CourseOut:
    """Create a course owned by this professor, with a fresh join code."""
    course = Course(
        title=body.title, professor_id=_user_uuid(professor), join_code=unused_join_code(db)
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    logger.info("Course created course_id=%s", course.id)
    return CourseOut.model_validate(course)


def list_courses(db: Session, professor: CurrentUser) -> list[CourseOut]:
    """List this professor's courses, oldest first, with how many students joined each."""
    student_count = (
        select(func.count(Enrollment.id))
        .where(Enrollment.course_id == Course.id)
        .correlate(Course)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Course, student_count)
        .where(Course.professor_id == _user_uuid(professor))
        .order_by(Course.created_at, Course.id)
    )
    return [
        CourseOut.model_validate(course).model_copy(update={"student_count": count})
        for course, count in rows
    ]


def join_course(db: Session, student: CurrentUser, body: JoinCourseIn) -> EnrollmentOut:
    """Join a course by its code. Joining again returns the same enrollment."""
    course = db.scalar(select(Course).where(Course.join_code == normalize_join_code(body.code)))
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=UNKNOWN_JOIN_CODE)
    student_id = _user_uuid(student)
    enrollment = _find_enrollment(db, course.id, student_id)
    if enrollment is None:
        db.add(Enrollment(course_id=course.id, student_id=student_id))
        try:
            db.commit()
        except IntegrityError:
            # Two joins at once: the other request created it.
            db.rollback()
        enrollment = _find_enrollment(db, course.id, student_id)
        if enrollment is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Couldn't join. Try again"
            )
        logger.info("Student joined course_id=%s", course.id)
    return EnrollmentOut(
        course_id=course.id, course_title=course.title, joined_at=enrollment.joined_at
    )


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
        questions=_questions(body),
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


def update_assignment(
    db: Session, professor: CurrentUser, assignment_id: uuid.UUID, body: AssignmentUpdate
) -> AssignmentOut:
    """Save a draft's edits. The questions replace the old list, in the order given."""
    assignment = _get_owned_assignment(db, professor, assignment_id)
    _require_draft(assignment)
    assignment.title = body.title
    assignment.instructions = body.instructions
    assignment.ai_policy = body.ai_policy
    assignment.help_level = body.help_level
    assignment.final_check = body.final_check
    # Positions are unique per assignment, so the old questions go before the new ones
    # arrive. Drafts have no submissions, so no student answers point at them.
    assignment.questions.clear()
    db.flush()
    assignment.questions.extend(_questions(body))
    db.commit()
    db.refresh(assignment)
    logger.info("Assignment updated assignment_id=%s", assignment.id)
    return AssignmentOut.model_validate(assignment)


def publish_assignment(
    db: Session, professor: CurrentUser, assignment_id: uuid.UUID
) -> AssignmentOut:
    """Publish a draft so students can start it. It can't be edited after this."""
    assignment = _get_owned_assignment(db, professor, assignment_id)
    _require_draft(assignment)
    assignment.published_at = datetime.now(UTC)
    db.commit()
    db.refresh(assignment)
    logger.info("Assignment published assignment_id=%s", assignment.id)
    return AssignmentOut.model_validate(assignment)


def _questions(body: AssignmentFields) -> list[Question]:
    return [
        Question(
            position=position,
            prompt=question.prompt,
            answer_type=question.answer_type,
            language=question.language,
            starter_code=question.starter_code,
        )
        for position, question in enumerate(body.questions, start=1)
    ]


def upload_assignment_pdf(
    db: Session, professor: CurrentUser, assignment_id: uuid.UUID, file: BinaryIO
) -> AssignmentOut:
    """Store a PDF for one of this professor's assignments and record where it is."""
    assignment = _get_owned_assignment(db, professor, assignment_id)
    _require_draft(assignment)
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


def _require_draft(assignment: Assignment) -> None:
    # Students may already be working on a published assignment, so it stays as it is.
    if assignment.published_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_PUBLISHED)


def unused_join_code(db: Session) -> str:
    """A join code no course has yet. Also used by the demo seed script."""
    # About 500 billion codes, so a clash is rare; the unique constraint is the backstop.
    while True:
        code = new_join_code()
        if db.scalar(select(Course.id).where(Course.join_code == code)) is None:
            return code


def _find_enrollment(db: Session, course_id: uuid.UUID, student_id: uuid.UUID) -> Enrollment | None:
    return db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.student_id == student_id
        )
    )


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
