"""OutlineNode: generate module/lesson outline from parsed intake (PRD T-002)."""

import json
import os

from langchain_openai import ChatOpenAI

from syllabus.models.schemas import LessonOutline, ModuleOutline, ParsedIntake


def _parse_outline_response(content: str) -> list[ModuleOutline]:
    """Parse LLM response into list of ModuleOutline."""
    content = content.strip()
    if "```" in content:
        for part in content.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                data = json.loads(part)
                break
        else:
            data = json.loads(content)
    else:
        data = json.loads(content)
    modules = []
    for m in data.get("modules", []):
        lessons = [
            LessonOutline(title=lev.get("title", ""), objective=lev.get("objective", ""))
            for lev in m.get("lessons", [])
        ]
        modules.append(
            ModuleOutline(
                title=m.get("title", ""),
                objective=m.get("objective", ""),
                lessons=lessons,
            )
        )
    return modules


def run_outline(parsed: ParsedIntake, llm: ChatOpenAI | None = None) -> list[ModuleOutline]:
    """Generate course outline (modules + lesson titles/objectives only)."""
    if not llm:
        llm = ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL_OUTLINE", "gpt-4o"),
            temperature=0.3,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    prompt = f"""You are a fertility education course designer. Create a short course outline for this patient profile.
Output ONLY valid JSON with this structure (no markdown):
{{ "modules": [ {{ "title": "...", "objective": "...", "lessons": [ {{ "title": "...", "objective": "..." }} ] }} ] }}

Patient profile:
- Journey stage: {parsed.journey_stage}
- Diagnosis: {parsed.diagnosis or "Not specified"}
- Main confusion: {parsed.confusion}
- Knowledge level: {parsed.level}

Requirements:
- 2 to 4 modules, 2 to 5 lessons per module. Total 6-12 lessons.
- Titles and objectives only; no lesson content.
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
