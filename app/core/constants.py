"""Shared fixed values. Change them here, not inline in features."""

from enum import StrEnum


class Step(StrEnum):
    ATTEMPT = "attempt"
    FEEDBACK = "feedback"
    EVALUATE = "evaluate"
    REVISE = "revise"
    EXPLAIN = "explain"


class AIPolicy(StrEnum):
    PROHIBITED = "prohibited"
    PERMITTED = "permitted"
    EXPECTED = "expected"


class HelpLevel(StrEnum):
    HINTS = "hints"
    APPROACH = "approach"
    CONCEPTS = "concepts"


class FinalCheck(StrEnum):
    AI_INTERVIEW = "ai_interview"
    QUESTIONNAIRE = "questionnaire"


class ReviewPriority(StrEnum):
    ROUTINE = "routine"
    WORTH_REVIEWING = "worth_reviewing"
    NEEDS_CONVERSATION = "needs_conversation"


class AnswerType(StrEnum):
    """How a question is answered. The frontend mirrors this in lib/constants.ts."""

    CODE = "code"
    TEXT = "text"
    MATH = "math"


class SubmissionStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"


class EvaluationVerdict(StrEnum):
    """The student's judgement of the AI feedback in the evaluate step."""

    CORRECT = "correct"
    PARTLY_CORRECT = "partly_correct"
    INCORRECT = "incorrect"


class ActivityEventType(StrEnum):
    """What a work session records. Signals that give the professor context, never flags."""

    PASTE = "paste"
    TAB_LEAVE = "tab_leave"
    TAB_RETURN = "tab_return"
    # Recorded by the backend on every answer save; the browser can't send these.
    SNAPSHOT = "snapshot"


class Role(StrEnum):
    STUDENT = "student"
    PROFESSOR = "professor"


MAX_PDF_MB = 10

# Work sessions: the most events one request may send, and how long a session can sit
# idle before the next activity starts a new one.
MAX_EVENTS_PER_BATCH = 100
SESSION_IDLE_MINUTES = 30

RATE_LIMIT_DEFAULT = "60/minute"
RATE_LIMIT_AI = "20/minute"
RATE_LIMIT_PDF_UPLOAD = "10/hour"
# Sign-up, log-in, refresh and log-out. Low, to slow down password guessing.
RATE_LIMIT_AUTH = "10/minute"

# Session cookies. The frontend's SESSION_COOKIES uses the same names.
ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"
# Supabase refresh tokens are single-use and rotate on every refresh, so a long
# cookie lifetime only keeps an active person logged in.
REFRESH_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
