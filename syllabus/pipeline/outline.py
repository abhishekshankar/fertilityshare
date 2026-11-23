"""OutlineNode: generate module/lesson outline from parsed intake (PRD T-002, Addendum P1/P2/P3/D1/D2/D4)."""

import json
import os

from langchain_openai import ChatOpenAI

from syllabus.models.schemas import LessonOutline, ModuleOutline, ParsedIntake
from syllabus.pipeline.prompts import PEDAGOGY_PREAMBLE, learner_objective_line


def _extract_json_data(content: str) -> dict:
    """Extract JSON dict from LLM response that may contain markdown code blocks."""
    content = content.strip()
    if "```" in content:
        for part in content.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                return json.loads(part)
        return json.loads(content)
    return json.loads(content)


_VALID_KNOWLEDGE_TYPES = {"declarative", "procedural", "conditional"}
_VALID_SENSITIVITY_LEVELS = {"low", "medium", "high"}


def _parse_lesson_outline(lev: dict) -> LessonOutline:
    """Parse a single lesson dict into a LessonOutline."""
    kt = (lev.get("knowledge_type") or "declarative").lower()
    if kt not in _VALID_KNOWLEDGE_TYPES:
        kt = "declarative"
    es = (lev.get("emotional_sensitivity_level") or "low").lower()
    if es not in _VALID_SENSITIVITY_LEVELS:
        es = "low"
    return LessonOutline(
        title=lev.get("title", ""),
        objective=lev.get("objective", ""),
        knowledge_type=kt,
        emotional_sensitivity_level=es,
    )


def _parse_outline_response(content: str) -> list[ModuleOutline]:
    """Parse LLM response into list of ModuleOutline."""
    data = _extract_json_data(content)
    return [
        ModuleOutline(
            title=m.get("title", ""),
            objective=m.get("objective", ""),
            lessons=[_parse_lesson_outline(lev) for lev in m.get("lessons", [])],
        )
        for m in data.get("modules", [])
    ]


def run_outline(parsed: ParsedIntake, llm: ChatOpenAI | None = None) -> list[ModuleOutline]:
    """Generate course outline (modules + lesson titles/objectives + knowledge_type)."""
    if not llm:
        llm = ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL_OUTLINE", "gpt-4o"),
            temperature=0.3,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    objective_line = learner_objective_line(parsed.target_end_state or "")
    prompt = f"""{PEDAGOGY_PREAMBLE}

You are a fertility education course designer. Create a short course outline for this patient profile.
Design the course arc backward from the learner's objective. The final lesson targets the goal directly. Each prior lesson scaffolds exactly the knowledge needed to understand the next. If a potential lesson does not serve the arc, discard it even if it is topically relevant.
The learner should feel the arc is achievable. Fewer modules that each land a clear milestone are better than comprehensive coverage. Maximum 4 modules, 3–5 lessons per module. Each lesson adds exactly ONE new layer of understanding.
Detect the primary knowledge topology of this course: procedural, conceptual, clinical/healthcare, or emotional/processing. Tag each lesson with knowledge_type accordingly.

{objective_line}Patient profile:
- Journey stage: {parsed.journey_stage}
- Diagnosis: {parsed.diagnosis or "Not specified"}
- Main confusion: {parsed.confusion}
- Knowledge level: {parsed.level}

Output ONLY valid JSON with this structure (no markdown):
{{ "modules": [ {{ "title": "...", "objective": "...", "lessons": [ {{ "title": "...", "objective": "...", "knowledge_type": "declarative" | "procedural" | "conditional", "emotional_sensitivity_level": "low" | "medium" | "high" }} ] }} ] }}

Requirements:
- 2 to 4 modules, 2 to 5 lessons per module. Total 6-12 lessons.
- Titles and objectives only; no lesson content.
- Each lesson must have knowledge_type: "declarative" (facts/concepts), "procedural" (skills/sequences), or "conditional" (when/why to apply).
- Each lesson must have emotional_sensitivity_level: "high" for emotionally loaded topics (failed cycles, grief, loss, disappointment, processing bad news); "medium" for anxiety or uncertainty; "low" for factual/procedural only. This drives whether the lesson gets a quiz (low/medium) or reflection only (high).
- Objectives should be one sentence each.
- Last lesson of the course should prepare "what to ask your RE" (we'll add a compliance note there).
- Empathetic, medically grounded tone.

JSON:"""
    response = llm.invoke(prompt)
    return _parse_outline_response(response.content)


def outline_node(state: dict) -> dict:
    """LangGraph node: state must have parsed_intake."""
    parsed = state.get("parsed_intake")
    if parsed is None and not state.get("error"):
        return {"error": "Missing parsed_intake"}
    if state.get("error"):
        return {}
    if isinstance(parsed, dict):
        parsed = ParsedIntake.model_validate(parsed)
    try:
        outline = run_outline(parsed)
        return {"outline": outline, "error": None}
    except Exception as e:
        return {"error": str(e), "outline": None}
