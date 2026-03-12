"""LangGraph orchestration: Intent -> Outline -> Research -> Content -> QA (PRD 5.2)."""

import queue
from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from syllabus.models.schemas import CourseSpec, IntakeData, Metadata, Module, ParsedIntake
from syllabus.pipeline.content import _flat_lessons, content_node, run_content_for_lesson
from syllabus.pipeline.intent import intent_node
from syllabus.pipeline.outline import outline_node
from syllabus.pipeline.qa import qa_node, run_qa_for_lesson
from syllabus.pipeline.research import research_node
from syllabus.pipeline.state import PipelineState


def build_graph() -> StateGraph:
    """Build the pipeline graph."""
    builder = StateGraph(PipelineState)
    builder.add_node("intent", intent_node)
    builder.add_node("outline", outline_node)
    builder.add_node("research", research_node)
    builder.add_node("content", content_node)
    builder.add_node("qa", qa_node)
    builder.add_edge(START, "intent")
    builder.add_edge("intent", "outline")
    builder.add_edge("outline", "research")
    builder.add_edge("research", "content")
    builder.add_edge("content", "qa")
    builder.add_edge("qa", END)
    return builder


def run_pipeline(raw_intake: str | dict) -> CourseSpec | None:
    """
    Run the full pipeline and return CourseSpec on success, None on failure.
    """
    graph = build_graph().compile()
    initial: PipelineState = {"raw_intake": raw_intake}
    result = graph.invoke(initial)
    spec = result.get("course_spec")
    if result.get("qa_passed") and spec is not None:
        return spec
    return None


# Map node names to SSE message and progress (0-100)
STREAM_MESSAGES = {
    "intent": ("Parsing your intake...", 10),
    "outline": ("Building outline...", 25),
    "research": ("Gathering key facts...", 40),
    "content": ("Writing lessons...", 60),
    "qa": ("Finalizing and checking...", 90),
}


def stream_pipeline(
    raw_intake: str | dict,
    callback: Callable[[str, dict], None] | None = None,
) -> dict | None:
    """
    Run pipeline with streaming; call callback(node_name, state) for each node.
    callback is sync (called from same thread). Returns course_spec dict if success, else None.
    """
    graph = build_graph().compile()
    initial: PipelineState = {"raw_intake": raw_intake}
    last_state: dict | None = None
    for chunk in graph.stream(initial):
        for node_name, state in chunk.items():
            last_state = dict(state) if state else last_state
            if callback is not None and node_name:
                callback(node_name, last_state or {})
    if last_state and last_state.get("qa_passed") and last_state.get("course_spec"):
        spec = last_state["course_spec"]
        return spec.model_dump(mode="json") if hasattr(spec, "model_dump") else spec
    return None


def _build_intake_data(parsed: object) -> IntakeData:
    """Convert parsed intake (any shape) to IntakeData."""
    if parsed is None:
        return IntakeData(journey_stage="", confusion="", level="beginner")
    if isinstance(parsed, IntakeData):
        return parsed
    if isinstance(parsed, dict):
        return IntakeData(
            journey_stage=parsed.get("journey_stage", ""),
            diagnosis=parsed.get("diagnosis"),
            confusion=parsed.get("confusion", ""),
            level=parsed.get("level", "beginner"),
            target_end_state=parsed.get("target_end_state", ""),
        )
    d = parsed.model_dump() if hasattr(parsed, "model_dump") else vars(parsed)
    return IntakeData(
        journey_stage=d.get("journey_stage", ""),
        diagnosis=d.get("diagnosis"),
        confusion=d.get("confusion", ""),
        level=d.get("level", "beginner"),
        target_end_state=d.get("target_end_state", ""),
    )


def stream_pipeline_progressive(
    raw_intake: str | dict,
    sync_queue: queue.Queue,
) -> None:
    """
    Run pipeline with progressive per-lesson delivery (F-016).

    Puts typed tuples into sync_queue:
      ("node", node_name)
      ("outline_ready", [module_dicts])
      ("lesson_ready", mod_idx, les_idx, lesson_dict)
      ("__done__", course_spec_dict)
      ("__error__", message)
    """
    try:
        state: dict = {"raw_intake": raw_intake}

        result = intent_node(state)
        state.update(result)
        sync_queue.put(("node", "intent"))
        if state.get("error"):
            sync_queue.put(("__error__", state["error"]))
            return

        result = outline_node(state)
        state.update(result)
        if state.get("error"):
            sync_queue.put(("__error__", state["error"]))
            return

        outline = state["outline"]
        parsed = state["parsed_intake"]

        outline_data = [
            {
                "id": str(mod.id),
                "title": mod.title,
                "objective": mod.objective,
                "lessons": [
                    {
                        "id": str(les.id),
                        "title": les.title,
                        "objective": les.objective,
                        "status": "queued",
                    }
                    for les in mod.lessons
                ],
            }
            for mod in outline
        ]
        sync_queue.put(("outline_ready", outline_data))

        result = research_node(state)
        state.update(result)
        sync_queue.put(("node", "research"))

        research = state.get("research") or {}
        research_citations = state.get("research_citations") or {}

        if isinstance(parsed, dict):
            parsed = ParsedIntake.model_validate(parsed)

        flat = _flat_lessons(outline)
        total = len(flat)
        all_lessons: dict[str, list] = {}

        for idx, (mod_out, lec_out, one_based) in enumerate(flat):
            mod_idx = next(i for i, m in enumerate(outline) if m.id == mod_out.id)
            les_idx = next(i for i, l_out in enumerate(mod_out.lessons) if l_out.id == lec_out.id)

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
                citations=citations or None,
                position_in_arc=position_in_arc,
                adjacent_lessons=adjacent_lessons,
            )

            passed, _msg = run_qa_for_lesson(lesson)
            if not passed:
                # V1.1: still emit; retry/refinement loop deferred to V3
                pass

            lesson_dict = lesson.model_dump(mode="json")

            mod_id = str(mod_out.id)
            if mod_id not in all_lessons:
                all_lessons[mod_id] = []
            all_lessons[mod_id].append(lesson)

            sync_queue.put(("lesson_ready", mod_idx, les_idx, lesson_dict))

        modules = []
        for mod_out in outline:
            mod_id = str(mod_out.id)
            modules.append(
                Module(
                    id=mod_out.id,
                    title=mod_out.title,
                    objective=mod_out.objective,
                    lessons=all_lessons.get(mod_id, []),
                )
            )

        intake_data = _build_intake_data(parsed)
        title = modules[0].title if len(modules) == 1 else "Your fertility learning course"

        course_spec = CourseSpec(
            title=title,
            intake=intake_data,
            modules=modules,
            metadata=Metadata(pipeline_version="0.1.0"),
        )
        sync_queue.put(("__done__", course_spec.model_dump(mode="json")))
    except Exception as exc:
        sync_queue.put(("__error__", str(exc)))
