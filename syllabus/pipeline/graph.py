"""LangGraph orchestration: Intent -> Outline -> Research -> Content -> QA (PRD 5.2)."""

from langgraph.graph import END, START, StateGraph

from syllabus.models.schemas import CourseSpec
from syllabus.pipeline.content import content_node
from syllabus.pipeline.intent import intent_node
from syllabus.pipeline.outline import outline_node
from syllabus.pipeline.qa import qa_node
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
    callback: None = None,
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
            if callback and node_name:
                callback(node_name, last_state or {})
    if last_state and last_state.get("qa_passed") and last_state.get("course_spec"):
        spec = last_state["course_spec"]
        return spec.model_dump(mode="json") if hasattr(spec, "model_dump") else spec
    return None
