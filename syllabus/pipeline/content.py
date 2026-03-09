"""ContentNode: generate lesson content (blocks) including compliance_note (PRD T-004)."""

import json
import os

from langchain_openai import ChatOpenAI

from syllabus.models.schemas import (
    Citation,
    ContentBlock,
    ContentBlockType,
    Lesson,
    LessonOutline,
    Module,
    ModuleOutline,
    ParsedIntake,
)


def _parse_blocks(content: str) -> list[ContentBlock]:
    """Parse LLM response into list of ContentBlock; ensure compliance_note at end."""
    content = content.strip()
    if "```" in content:
        for part in content.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("["):
                raw = json.loads(part)
                break
            if part.startswith("{") and "blocks" in part:
                raw = json.loads(part).get("blocks", [])
                break
        else:
            raw = json.loads(content) if content.startswith("[") else []
    else:
        try:
            raw = json.loads(content)
            if isinstance(raw, dict) and "blocks" in raw:
                raw = raw["blocks"]
        except json.JSONDecodeError:
            raw = []
    blocks = []
    for b in raw:
        bt = (b.get("type") or "explanation").lower().replace(" ", "_")
        if bt not in ("explanation", "example", "exercise", "reflection", "compliance_note"):
            bt = "explanation"
        blocks.append(
            ContentBlock(
                type=ContentBlockType(bt),
                content=(b.get("content") or "").strip() or "(No content)",
            )
        )
    # Ensure compliance_note at end (PRD F-003)
    has_compliance = any(b.type == ContentBlockType.compliance_note for b in blocks)
    if not has_compliance:
        blocks.append(
            ContentBlock(
                type=ContentBlockType.compliance_note,
                content="Ask your RE: What should I focus on given my situation? What follow-up do you recommend?",
            )
        )
    else:
        # Move compliance_note to end if present elsewhere
        compliance_blocks = [b for b in blocks if b.type == ContentBlockType.compliance_note]
        others = [b for b in blocks if b.type != ContentBlockType.compliance_note]
        blocks = others + compliance_blocks[-1:]  # keep last compliance at end
    return blocks


def run_content_for_lesson(
    lesson_outline: LessonOutline,
    research_facts: str,
    parsed: ParsedIntake,
    llm: ChatOpenAI | None = None,
    citations: list[dict] | None = None,
) -> Lesson:
    """Generate full lesson with blocks (including compliance_note)."""
    if not llm:
        llm = ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL_CONTENT", "gpt-4o"),
            temperature=0.4,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    prompt = f"""You are a warm, empathetic fertility educator. Write ONE lesson as JSON.

Lesson title: {lesson_outline.title}
Lesson objective: {lesson_outline.objective}

Context: Patient journey stage: {parsed.journey_stage}. Diagnosis: {parsed.diagnosis or "Not specified"}. Level: {parsed.level}.
Key facts to ground the lesson: {research_facts}

Output ONLY valid JSON with a "blocks" array. Each block: {{ "type": "...", "content": "..." }}.
Block types: explanation, example, exercise, reflection, compliance_note.
- Use 2-5 explanation/example/exercise/reflection blocks for the lesson body.
- You MUST include exactly one block with type "compliance_note" at the END. Its content must be 1-3 questions the patient can ask their RE (e.g. "What should I ask my RE?"). Never give prescriptive medical advice (e.g. do not say "you should take X mg").
- Content: clear, warm, medically accurate, non-prescriptive.

JSON:"""
    response = llm.invoke(prompt)
    blocks = _parse_blocks(response.content)
    if citations and blocks:
        cite_models = [Citation(source=c.get("source"), snippet=c.get("snippet")) for c in citations]
        first = blocks[0]
        blocks = [ContentBlock(type=first.type, content=first.content, citations=cite_models)] + blocks[1:]
    return Lesson(
        id=lesson_outline.id,
        title=lesson_outline.title,
        objective=lesson_outline.objective,
        blocks=blocks,
    )


def run_content(
    outline: list[ModuleOutline],
    research: dict[str, str],
    parsed: ParsedIntake,
    llm: ChatOpenAI | None = None,
    research_citations: dict[str, list[dict]] | None = None,
) -> list[Module]:
    """Generate content for all lessons; return list of Module with filled Lesson list."""
    research_citations = research_citations or {}
    modules = []
    for mod_out in outline:
        lessons = []
        for lec_out in mod_out.lessons:
            facts = research.get(str(lec_out.id), "")
            citations = research_citations.get(str(lec_out.id), [])
            lesson = run_content_for_lesson(lec_out, facts, parsed, llm=llm, citations=citations or None)
            lessons.append(lesson)
        modules.append(
            Module(
                id=mod_out.id,
                title=mod_out.title,
                objective=mod_out.objective,
                lessons=lessons,
            )
        )
    return modules


def content_node(state: dict) -> dict:
    """LangGraph node: state must have outline, research, parsed_intake."""
    outline = state.get("outline")
    research = state.get("research") or {}
    research_citations = state.get("research_citations") or {}
    parsed = state.get("parsed_intake")
    if not outline or parsed is None and not state.get("error"):
        return {"error": state.get("error") or "Missing outline or parsed_intake"}
    if state.get("error"):
        return {}
    if isinstance(parsed, dict):
        parsed = ParsedIntake.model_validate(parsed)
    try:
        modules = run_content(outline, research, parsed, research_citations=research_citations)
        return {"modules": modules, "error": None}
    except Exception as e:
        return {"error": str(e), "modules": None}
