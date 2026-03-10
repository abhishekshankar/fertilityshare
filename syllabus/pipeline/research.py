"""ResearchNode: RAG retrieval per lesson with stub fallback (PRD T-013)."""

from syllabus.models.schemas import ModuleOutline
from syllabus.rag.store import query_facts


def run_research_stub(outline: list[ModuleOutline]) -> tuple[dict[str, str], dict[str, list[dict]]]:
    """Fallback: return placeholder facts and no citations."""
    facts = {}
    for mod in outline:
        for lesson in mod.lessons:
            facts[str(lesson.id)] = (
                "Key concepts and evidence-based points for this topic (RAG fallback)."
            )
    return facts, {}


def run_research(
    outline: list[ModuleOutline], intake_context: str
) -> tuple[dict[str, str], dict[str, list[dict]]]:
    """
    For each lesson, query RAG with title/objective + intake context.
    Returns (lesson_id -> facts string, lesson_id -> list of {source, snippet}).
    On RAG failure or empty index, falls back to stub.
    """
    research = {}
    citations = {}
    for mod in outline:
        for lesson in mod.lessons:
            query = f"{lesson.title}. {lesson.objective}"
            try:
                facts_str, cites = query_facts(query, intake_context=intake_context)
                research[str(lesson.id)] = facts_str
                citations[str(lesson.id)] = cites
            except Exception:
                research[str(lesson.id)] = (
                    "Key concepts and evidence-based points for this topic (RAG fallback)."
                )
                citations[str(lesson.id)] = []
    return research, citations


def research_node(state: dict) -> dict:
    """LangGraph node: state must have outline. Uses RAG with stub fallback."""
    outline = state.get("outline")
    if outline is None and not state.get("error"):
        return {"error": "Missing outline"}
    if state.get("error"):
        return {}
    parsed = state.get("parsed_intake")
    intake_context = ""
    if parsed:
        if hasattr(parsed, "journey_stage"):
            intake_context = f"Journey: {parsed.journey_stage}. Diagnosis: {parsed.diagnosis or 'Not specified'}. Level: {parsed.level}."
        elif isinstance(parsed, dict):
            intake_context = f"Journey: {parsed.get('journey_stage', '')}. Diagnosis: {parsed.get('diagnosis') or 'Not specified'}."
    try:
        research, research_citations = run_research(outline, intake_context)
        return {"research": research, "research_citations": research_citations, "error": None}
    except Exception as e:
        research, research_citations = run_research_stub(outline)
        return {"research": research, "research_citations": research_citations, "error": str(e)}
