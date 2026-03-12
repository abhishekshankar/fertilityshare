"""ContentNode: generate lesson content (blocks) including compliance_note (PRD T-004, Addendum P1–P7/P9)."""

import json
import os
import re

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
from syllabus.pipeline.prompts import PEDAGOGY_PREAMBLE, learner_objective_line


def _strip_thinking(text: str) -> str:
    """Remove <thinking>...</thinking> from LLM output (P6); parse only the JSON part."""
    if "<thinking>" in text and "</thinking>" in text:
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
    return text.strip()


def _extract_json(content: str) -> dict:
    """Extract JSON object from LLM response (handles markdown code blocks)."""
    content = content.strip()
    if "```" in content:
        for part in content.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                return json.loads(part)
            if part.startswith("["):
                return {"blocks": json.loads(part)}
        return {}
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {"blocks": data}
    except json.JSONDecodeError:
        return {}


def _parse_blocks(
    content: str,
    default_emotional_sensitivity: str = "low",
) -> tuple[list[ContentBlock], list[str]]:
    """Parse LLM response into blocks and key_takeaways; ensure compliance_note at end. Returns (blocks, key_takeaways)."""
    data = _extract_json(content)
    raw = data.get("blocks", [])
    if not raw and isinstance(data.get("blocks"), list):
        raw = data["blocks"]
    key_takeaways = data.get("key_takeaways") or []
    if isinstance(key_takeaways, list):
        key_takeaways = [str(x).strip() for x in key_takeaways if x][:5]
    else:
        key_takeaways = []

    blocks = []
    for b in raw:
        bt = (b.get("type") or "explanation").lower().replace(" ", "_")
        if bt not in ("explanation", "example", "exercise", "reflection", "compliance_note"):
            bt = "explanation"
        es = (b.get("emotional_sensitivity_level") or default_emotional_sensitivity).lower()
        if es not in ("low", "medium", "high"):
            es = default_emotional_sensitivity
        blocks.append(
            ContentBlock(
                type=ContentBlockType(bt),
                content=(b.get("content") or "").strip() or "(No content)",
                emotional_sensitivity_level=es,
            )
        )
    # Ensure compliance_note at end (PRD F-003)
    has_compliance = any(b.type == ContentBlockType.compliance_note for b in blocks)
    if not has_compliance:
        blocks.append(
            ContentBlock(
                type=ContentBlockType.compliance_note,
                content="Ask your RE: What should I focus on given my situation? What follow-up do you recommend?",
                emotional_sensitivity_level=default_emotional_sensitivity,
            )
        )
    else:
        compliance_blocks = [b for b in blocks if b.type == ContentBlockType.compliance_note]
        others = [b for b in blocks if b.type != ContentBlockType.compliance_note]
        blocks = others + compliance_blocks[-1:]
    return blocks, key_takeaways


def run_content_for_lesson(
    lesson_outline: LessonOutline,
    research_facts: str,
    parsed: ParsedIntake,
    llm: ChatOpenAI | None = None,
    citations: list[dict] | None = None,
    position_in_arc: str = "",
    adjacent_lessons: list[tuple[str, str]] | None = None,
) -> Lesson:
    """Generate full lesson with blocks (P1/P2/P3/P6/P7/P9: objective, reasoning, tone, arc-only context)."""
    if not llm:
        llm = ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL_CONTENT", "gpt-4o"),
            temperature=0.4,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    objective_line = learner_objective_line(getattr(parsed, "target_end_state", "") or "")
    kt = getattr(lesson_outline, "knowledge_type", "declarative") or "declarative"
    es_level = getattr(lesson_outline, "emotional_sensitivity_level", "low") or "low"
    if es_level not in ("low", "medium", "high"):
        es_level = "low"
    kt_instruction = {
        "declarative": "Use explanation → elaboration → example → recall-style exercise. No trick questions.",
        "procedural": "Use step-by-step structure, demonstration description, and a practice scenario.",
        "conditional": "Use case-based scenarios, decision-tree framing, and a reflection prompt.",
    }.get(kt, "Use explanation, example, and exercise blocks.")
    # Format selection (F-011): high emotional sensitivity → reflection instead of quiz-style exercise
    if es_level == "high":
        kt_instruction += " This lesson is emotionally sensitive: use a reflection block instead of a recall-style exercise; no quiz-style questions. End with supportive, patient-first framing."
    adjacent_text = ""
    if adjacent_lessons:
        adjacent_text = (
            "Adjacent lessons (titles and objectives only; do not repeat their content):\n"
        )
        for title, obj in adjacent_lessons:
            adjacent_text += f"- {title}: {obj}\n"
        adjacent_text += "\n"
    prompt = f"""{PEDAGOGY_PREAMBLE}

You are a fertility education content writer. Your role is only to write this one lesson's content. Do not decide quiz/format placement; only write blocks. Write as a warm, knowledgeable friend who has been through IVF and understands the science. Accessible but intelligent; no jargon without explanation. For exercise blocks: be a tutor checking understanding, supportive not evaluative. For the compliance_note block: write as a caring nurse explaining what to bring up at the next appointment — empowering, not alarming.

{objective_line}Before writing this lesson, reason through the following steps. Include your reasoning in <thinking>...</thinking> tags (they will be stripped from output):
1. What is the learner's objective for this course?
2. What does the learner already know at this point in the arc (from prior lessons)?
3. What is the single concept this lesson must add?
4. What is the most common misconception about this concept?
5. What is the minimum vocabulary the learner needs?
6. Now write the lesson.

Lesson title: {lesson_outline.title}
Lesson objective: {lesson_outline.objective}
{f"Position in course: {position_in_arc}" if position_in_arc else ""}

This lesson is tagged as {kt}. {kt_instruction}
Emotional sensitivity for this lesson: {es_level}.

Context: Patient journey stage: {parsed.journey_stage}. Diagnosis: {parsed.diagnosis or "Not specified"}. Level: {parsed.level}.
Key facts to ground the lesson: {research_facts}
{adjacent_text}
Output ONLY valid JSON with two keys: "key_takeaways" (array of 3-5 short strings, one line each, to display at TOP of lesson) and "blocks" (array of blocks). Each block: {{ "type": "...", "content": "...", optional "emotional_sensitivity_level": "low"|"medium"|"high" }}.
Block types: explanation, example, exercise, reflection, compliance_note.
- key_takeaways: 3-5 bullet-style takeaways that prime recall before the learner reads the full lesson.
- Use 2-5 explanation/example/exercise/reflection blocks for the lesson body.
- You MUST include exactly one block with type "compliance_note" at the END. Its content must be 1-3 questions the patient can ask their RE. Never give prescriptive medical advice.
- Content: clear, warm, medically accurate, non-prescriptive.

JSON:"""
    response = llm.invoke(prompt)
    raw_content = _strip_thinking(response.content)
    blocks, key_takeaways = _parse_blocks(raw_content, default_emotional_sensitivity=es_level)
    if citations and blocks:
        cite_models = [
            Citation(source=c.get("source"), snippet=c.get("snippet")) for c in citations
        ]
        first = blocks[0]
        blocks = [
            ContentBlock(
                type=first.type,
                content=first.content,
                citations=cite_models,
                emotional_sensitivity_level=first.emotional_sensitivity_level,
            )
        ] + blocks[1:]
    # Format selection (F-011): no quiz for high emotional sensitivity
    quiz = (
        None  # Quiz generation not yet implemented; when added, set to None when es_level == "high"
    )
    return Lesson(
        id=lesson_outline.id,
        title=lesson_outline.title,
        objective=lesson_outline.objective,
        blocks=blocks,
        key_takeaways=key_takeaways or [],
        knowledge_type=kt,
        emotional_sensitivity_level=es_level,
        quiz=quiz,
    )


def _flat_lessons(outline: list[ModuleOutline]) -> list[tuple[ModuleOutline, LessonOutline, int]]:
    """Flatten outline to (module, lesson, 1-based index) for position_in_arc. P9: arc-only context."""
    flat = []
    for mod_out in outline:
        for lec_out in mod_out.lessons:
            flat.append((mod_out, lec_out, len(flat) + 1))
    return flat


def run_content(
    outline: list[ModuleOutline],
    research: dict[str, str],
    parsed: ParsedIntake,
    llm: ChatOpenAI | None = None,
    research_citations: dict[str, list[dict]] | None = None,
) -> list[Module]:
    """Generate content for all lessons (P9: each lesson receives only arc context, no full text of others)."""
    research_citations = research_citations or {}
    flat = _flat_lessons(outline)
    total = len(flat)
    modules = []
    mod_lessons: list[Lesson] = []
    current_mod: ModuleOutline | None = None
    for idx, (mod_out, lec_out, one_based) in enumerate(flat):
        if mod_out != current_mod:
            if current_mod is not None:
                modules.append(
                    Module(
                        id=current_mod.id,
                        title=current_mod.title,
                        objective=current_mod.objective,
                        lessons=mod_lessons,
                    )
                )
            current_mod = mod_out
            mod_lessons = []
        position_in_arc = f"Lesson {one_based} of {total}"
        adjacent_lessons: list[tuple[str, str]] = []
        if idx > 0:
            _, prev_lec, _ = flat[idx - 1]
            adjacent_lessons.append((prev_lec.title, prev_lec.objective))
        if idx < total - 1:
            _, next_lec, _ = flat[idx + 1]
            adjacent_lessons.append((next_lec.title, next_lec.objective))
        facts = research.get(str(lec_out.id), "")
        citations = research_citations.get(str(lec_out.id), [])
        lesson = run_content_for_lesson(
            lec_out,
            facts,
            parsed,
            llm=llm,
            citations=citations or None,
            position_in_arc=position_in_arc,
            adjacent_lessons=adjacent_lessons,
        )
        mod_lessons.append(lesson)
    if current_mod is not None:
        modules.append(
            Module(
                id=current_mod.id,
                title=current_mod.title,
                objective=current_mod.objective,
                lessons=mod_lessons,
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
