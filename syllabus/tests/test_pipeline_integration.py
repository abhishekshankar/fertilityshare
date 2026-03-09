"""Integration test: pipeline from raw intake to CourseSpec (mocked LLMs)."""

import json
from unittest.mock import MagicMock, patch

from syllabus.models.schemas import ContentBlockType, CourseSpec, LessonOutline, ModuleOutline
from syllabus.pipeline import build_graph, run_pipeline


def _make_mock_outline() -> list[ModuleOutline]:
    return [
        ModuleOutline(
            title="Understanding PCOS",
            objective="Learn basics.",
            lessons=[
                LessonOutline(title="What is PCOS?", objective="Define PCOS."),
                LessonOutline(title="Next steps", objective="What to ask your RE."),
            ],
        ),
    ]


def _make_mock_content_response():
    return json.dumps(
        {
            "blocks": [
                {"type": "explanation", "content": "PCOS is a condition that affects ovulation."},
                {
                    "type": "compliance_note",
                    "content": "Ask your RE: What treatment options are right for me?",
                },
            ],
        }
    )


@patch("syllabus.pipeline.intent.ChatOpenAI")
@patch("syllabus.pipeline.outline.ChatOpenAI")
@patch("syllabus.pipeline.content.ChatOpenAI")
def test_pipeline_with_dict_intake_mocked(
    mock_content_llm_cls,
    mock_outline_llm_cls,
    mock_intent_llm_cls,
):
    """Run full pipeline with dict intake; mock LLMs to return valid outline and content."""
    # Intent: dict intake -> no LLM call; parsed_intake set
    # Outline: mock return structured outline
    mock_outline_llm = MagicMock()
    mock_outline_llm.invoke.return_value = MagicMock(
        content=json.dumps(
            {
                "modules": [
                    {
                        "title": "Understanding your situation",
                        "objective": "Learn basics.",
                        "lessons": [
                            {"title": "Overview", "objective": "Get oriented."},
                            {"title": "What to ask", "objective": "Questions for your RE."},
                        ],
                    },
                ],
            }
        ),
    )
    mock_outline_llm_cls.return_value = mock_outline_llm

    mock_content_llm = MagicMock()
    mock_content_llm.invoke.return_value = MagicMock(content=_make_mock_content_response())
    mock_content_llm_cls.return_value = mock_content_llm

    raw = {
        "journey_stage": "Preparing for first IVF",
        "diagnosis": "PCOS",
        "confusion": "stim protocols",
        "level": "beginner",
    }
    spec = run_pipeline(raw)
    assert spec is not None
    assert isinstance(spec, CourseSpec)
    assert len(spec.modules) >= 1
    for mod in spec.modules:
        for lesson in mod.lessons:
            assert len(lesson.blocks) >= 1
            compliance_blocks = [
                b for b in lesson.blocks if b.type == ContentBlockType.compliance_note
            ]
            assert len(compliance_blocks) >= 1, f"Lesson {lesson.title} missing compliance_note"
            assert any(
                "ask" in b.content.lower() or "re" in b.content.lower() for b in compliance_blocks
            )


def test_graph_builds_and_compiles():
    """Graph builds and compiles without error."""
    graph = build_graph().compile()
    assert graph is not None
