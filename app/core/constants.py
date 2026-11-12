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


class Role(StrEnum):
    STUDENT = "student"
    PROFESSOR = "professor"


MAX_PDF_MB = 10

RATE_LIMIT_DEFAULT = "60/minute"
RATE_LIMIT_AI = "20/minute"
RATE_LIMIT_PDF_UPLOAD = "10/hour"
