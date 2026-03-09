"""LangGraph state for the pipeline."""

from typing import Optional

from typing_extensions import TypedDict

from syllabus.models.schemas import (
    CourseSpec,
    Module,
    ModuleOutline,
    ParsedIntake,
)


class PipelineState(TypedDict, total=False):
    """State passed between pipeline nodes."""

    raw_intake: str | dict
    parsed_intake: Optional[ParsedIntake]
    outline: Optional[list[ModuleOutline]]
    research: Optional[dict[str, str]]  # lesson_id -> key facts
    research_citations: Optional[dict[str, list[dict]]]  # lesson_id -> [{source, snippet}]
    modules: Optional[list[Module]]
    course_spec: Optional[CourseSpec]
    qa_passed: bool
    error: Optional[str]
