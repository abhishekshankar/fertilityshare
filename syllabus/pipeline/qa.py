"""QANode: enforce compliance_note and flag prescriptive language (PRD T-005)."""

import os
import re

from langchain_openai import ChatOpenAI

from syllabus.models.schemas import ContentBlockType, CourseSpec, Lesson

# Rule-based prescriptive patterns (PRD: 100% catch rate for injected violations)
PRESCRIPTIVE_PATTERNS = [
    r"\byou\s+should\s+take\s+\d+\s*mg\b",
    r"\byou\s+must\s+take\b",
    r"\btake\s+\d+\s*mg\b",
    r"\bprescribe\s+yourself\b",
    r"\bI\s+recommend\s+you\s+(?:take|use|do)\b",
    r"\b(?:dosage|dose)\s+of\s+\d+",
    r"\bstart\s+(?:on|with)\s+\d+\s*mg\b",
    r"\b(?:you|patient)\s+should\s+(?:take|use|start)\s+",
]


def _has_prescriptive_language(text: str) -> bool:
    """Return True if text appears to contain prescriptive medical advice."""
    if not text:
        return False
    lower = text.lower()
    return any(re.search(pat, lower, re.IGNORECASE) for pat in PRESCRIPTIVE_PATTERNS)


def _lesson_has_compliance_note(lesson: Lesson) -> bool:
    """Check lesson has at least one compliance_note block with RE question."""
    for b in lesson.blocks:
        if (
            b.type == ContentBlockType.compliance_note
            and b.content
            and (
                "ask" in b.content.lower()
                or "re" in b.content.lower()
                or "doctor" in b.content.lower()
            )
        ):
            return True
    return False


def _lesson_has_no_prescriptive(lesson: Lesson) -> bool:
    """Check no block contains prescriptive language."""
    return all(not _has_prescriptive_language(b.content) for b in lesson.blocks)


def run_qa_rules(course_spec: CourseSpec) -> tuple[bool, str]:
    """
    Rule-based QA: every lesson has compliance_note, no prescriptive language.
    Returns (passed, message).
    """
    for mod in course_spec.modules:
        for lesson in mod.lessons:
            if not _lesson_has_compliance_note(lesson):
                return False, f"Lesson '{lesson.title}' missing compliance_note or RE question"
            if not _lesson_has_no_prescriptive(lesson):
                return False, f"Lesson '{lesson.title}' contains prescriptive language"
    return True, "OK"


def run_qa_llm(lesson: Lesson, llm: ChatOpenAI | None = None) -> tuple[bool, str]:
    """Optional LLM check for prescriptive tone (gpt-4o-mini)."""
    if not llm:
        llm = ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL_QA", "gpt-4o-mini"),
            temperature=0,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    text = "\n".join(b.content for b in lesson.blocks)
    prompt = f"""Does this lesson text contain any prescriptive medical advice (e.g. "you should take X mg", specific dosage, or telling the patient to start a treatment)? Answer ONLY yes or no.

Lesson text:
{text[:3000]}

Answer:"""
    response = llm.invoke(prompt)
    answer = (response.content or "").strip().lower()
    if "yes" in answer:
        return False, "LLM flagged possible prescriptive content"
    return True, "OK"


def run_qa_for_lesson(lesson: Lesson) -> tuple[bool, str]:
    """Run QA checks on a single lesson. Returns (passed, message)."""
    if not _lesson_has_compliance_note(lesson):
        return False, f"Lesson '{lesson.title}' missing compliance_note or RE question"
    if not _lesson_has_no_prescriptive(lesson):
        return False, f"Lesson '{lesson.title}' contains prescriptive language"
    return True, "OK"


def run_qa(course_spec: CourseSpec, use_llm: bool = False) -> tuple[bool, str]:
    """
    Run full QA: rules first, then optionally LLM per lesson.
    Returns (passed, message).
    """
    passed, msg = run_qa_rules(course_spec)
    if not passed:
        return False, msg
    if use_llm:
        for mod in course_spec.modules:
            for lesson in mod.lessons:
                passed, msg = run_qa_llm(lesson)
                if not passed:
                    return False, f"{lesson.title}: {msg}"
    return True, "OK"


def qa_node(state: dict) -> dict:
    """LangGraph node: build CourseSpec from modules + intake, then run QA."""
    modules = state.get("modules")
    parsed = state.get("parsed_intake")
    if not modules and not state.get("error"):
        return {"error": "Missing modules", "qa_passed": False}
    if state.get("error"):
        return {"qa_passed": False}
    # Build CourseSpec (title from first module or intake)
    from syllabus.models.schemas import IntakeData, Metadata

    if parsed is None:
        intake = IntakeData(
            journey_stage="", diagnosis=None, confusion="", level="beginner", target_end_state=""
        )
    elif isinstance(parsed, IntakeData):
        intake = parsed
    elif isinstance(parsed, dict):
        intake = IntakeData(
            journey_stage=parsed.get("journey_stage", ""),
            diagnosis=parsed.get("diagnosis"),
            confusion=parsed.get("confusion", ""),
            level=parsed.get("level", "beginner"),
            target_end_state=parsed.get("target_end_state", ""),
        )
    else:
        # ParsedIntake or any model with same shape (P2: include target_end_state)
        d = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
        intake = IntakeData(
            journey_stage=d.get("journey_stage", ""),
            diagnosis=d.get("diagnosis"),
            confusion=d.get("confusion", ""),
            level=d.get("level", "beginner"),
            target_end_state=d.get("target_end_state", ""),
        )
    title = "Your fertility learning course"
    if modules:
        title = modules[0].title if len(modules) == 1 else "Your fertility learning course"
    course_spec = CourseSpec(
        title=title,
        intake=intake,
        modules=modules,
        metadata=Metadata(pipeline_version="0.1.0"),
    )
    passed, msg = run_qa(course_spec, use_llm=False)
    return {
        "course_spec": course_spec if passed else None,
        "qa_passed": passed,
        "error": None if passed else msg,
    }
