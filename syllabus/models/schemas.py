"""Pydantic schemas for intake and CourseSpec (PRD Section 5.4)."""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ContentBlockType(str, Enum):
    """Atomic content block types."""

    explanation = "explanation"
    example = "example"
    exercise = "exercise"
    reflection = "reflection"
    compliance_note = "compliance_note"


class Citation(BaseModel):
    """Placeholder for V1 RAG citations."""

    source: Optional[str] = None
    snippet: Optional[str] = None


class ContentBlock(BaseModel):
    """Single block in a lesson."""

    type: ContentBlockType
    content: str
    citations: list[Citation] = Field(default_factory=list)


# --- Intake (API request shape + parsed intent) ---


class IntakeData(BaseModel):
    """Intake payload (POST /v1/generate request shape)."""

    journey_stage: str
    diagnosis: Optional[str] = None
    confusion: str
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"


class ParsedIntake(BaseModel):
    """Structured intake after IntentNode (sanitized, normalized)."""

    journey_stage: str
    diagnosis: Optional[str] = None
    confusion: str
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"


# --- Outline (output of OutlineNode; no full content yet) ---


class LessonOutline(BaseModel):
    """Lesson skeleton: title and objective only."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    objective: str


class ModuleOutline(BaseModel):
    """Module skeleton: title, objective, lesson outlines."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    objective: str
    lessons: list[LessonOutline] = Field(default_factory=list)


# --- CourseSpec (full course artifact) ---


class Flashcard(BaseModel):
    """Single flashcard (front/back)."""

    front: str
    back: str


class QuizQuestion(BaseModel):
    """Single quiz question."""

    question: str
    options: list[str] = Field(default_factory=list)
    correct_index: int = 0
    explanation: Optional[str] = None


class Quiz(BaseModel):
    """Quiz for a lesson (V0 minimal)."""

    questions: list[QuizQuestion] = Field(default_factory=list)
    reflection: Optional[str] = None


class Lesson(BaseModel):
    """Full lesson with blocks, optional flashcards and quiz."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    objective: str
    blocks: list[ContentBlock] = Field(default_factory=list)
    flashcards: list[Flashcard] = Field(default_factory=list)
    quiz: Optional[Quiz] = None


class Module(BaseModel):
    """Module containing lessons."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    objective: str
    lessons: list[Lesson] = Field(default_factory=list)


class Metadata(BaseModel):
    """CourseSpec metadata."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pipeline_version: str = "0.1.0"
    model_versions: dict[str, str] = Field(default_factory=dict)


class CourseSpec(BaseModel):
    """Canonical course artifact produced by the pipeline."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    intake: IntakeData
    modules: list[Module] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)
