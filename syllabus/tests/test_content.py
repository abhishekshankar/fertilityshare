"""Unit tests for ContentNode (_parse_blocks, run_content_for_lesson, run_content, content_node)."""

from unittest.mock import MagicMock, patch

from syllabus.models.schemas import (
    ContentBlockType,
    LessonOutline,
    ModuleOutline,
    ParsedIntake,
)
from syllabus.pipeline.content import (
    _parse_blocks,
    _strip_thinking,
    content_node,
    run_content,
    run_content_for_lesson,
)


def test_parse_blocks_well_formed_array():
    content = """[
        {"type": "explanation", "content": "This is the intro."},
        {"type": "example", "content": "For instance..."},
        {"type": "compliance_note", "content": "Ask your RE: ..."}
    ]"""
    blocks, key_takeaways = _parse_blocks(content)
    assert len(blocks) == 3
    assert blocks[0].type == ContentBlockType.explanation
    assert blocks[0].content == "This is the intro."
    assert blocks[1].type == ContentBlockType.example
    assert blocks[2].type == ContentBlockType.compliance_note
    assert isinstance(key_takeaways, list)


def test_parse_blocks_with_blocks_key():
    content = '{"blocks": [{"type": "explanation", "content": "Only block"}], "key_takeaways": ["One point"]}'
    blocks, key_takeaways = _parse_blocks(content)
    assert len(blocks) >= 1
    assert blocks[0].type == ContentBlockType.explanation
    assert blocks[0].content == "Only block"
    assert key_takeaways == ["One point"]


def test_parse_blocks_empty_adds_compliance_note():
    content = "[]"
    blocks, key_takeaways = _parse_blocks(content)
    assert len(blocks) == 1
    assert blocks[0].type == ContentBlockType.compliance_note
    assert "RE" in blocks[0].content
    assert key_takeaways == []


def test_parse_blocks_unknown_type_defaults_explanation():
    content = '[{"type": "unknown_thing", "content": "Text"}]'
    blocks, _ = _parse_blocks(content)
    assert len(blocks) >= 1
    assert blocks[0].type == ContentBlockType.explanation


def test_parse_blocks_missing_content_defaults():
    content = '[{"type": "explanation"}]'
    blocks, _ = _parse_blocks(content)
    assert blocks[0].content == "(No content)"


def test_parse_blocks_markdown_code_block():
    content = """```json
    [{"type": "reflection", "content": "Reflect here"}]
    ```
    """
    blocks, _ = _parse_blocks(content)
    assert len(blocks) >= 1
    assert blocks[0].type == ContentBlockType.reflection
    assert any(b.type == ContentBlockType.compliance_note for b in blocks)


def test_strip_thinking_removes_tags():
    raw = '<thinking>Step 1. The objective is X.</thinking>\n[{"type": "explanation", "content": "Body"}]'
    out = _strip_thinking(raw)
    assert "<thinking>" not in out
    assert "Body" in out
    blocks, _ = _parse_blocks(out)
    assert len(blocks) >= 1
    assert blocks[0].content == "Body"


def test_parse_blocks_compliance_note_moved_to_end():
    content = """[
        {"type": "compliance_note", "content": "Ask RE first"},
        {"type": "explanation", "content": "Body"}
    ]"""
    blocks, _ = _parse_blocks(content)
    assert blocks[-1].type == ContentBlockType.compliance_note
    assert blocks[-1].content == "Ask RE first"


def test_run_content_for_lesson_mocked_llm():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = """{"key_takeaways": ["Takeaway 1"], "blocks": [
        {"type": "explanation", "content": "Lesson body."},
        {"type": "compliance_note", "content": "What should I ask my RE?"}
    ]}"""
    lesson_out = LessonOutline(title="IVF basics", objective="Understand protocol")
    parsed = ParsedIntake(
        journey_stage="Newly diagnosed",
        diagnosis="PCOS",
        confusion="Protocols",
        level="beginner",
    )
    result = run_content_for_lesson(lesson_out, "Facts here", parsed, llm=mock_llm)
    assert result.id == lesson_out.id
    assert result.title == lesson_out.title
    assert result.objective == lesson_out.objective
    assert len(result.blocks) >= 2
    assert any(b.type == ContentBlockType.compliance_note for b in result.blocks)
    assert result.key_takeaways == ["Takeaway 1"]
    mock_llm.invoke.assert_called_once()


def test_run_content_produces_modules():
    from syllabus.models.schemas import Lesson

    lesson_out = LessonOutline(title="L1", objective="O1")
    outline = [ModuleOutline(title="M1", objective="O1", lessons=[lesson_out])]
    research = {str(lesson_out.id): "Research facts"}
    parsed = ParsedIntake(journey_stage="x", diagnosis=None, confusion="y", level="beginner")

    def make_lesson(lo, _f, _p, **kw):
        return Lesson(
            id=lo.id,
            title=lo.title,
            objective=lo.objective,
            blocks=[],
            key_takeaways=[],
            knowledge_type=getattr(lo, "knowledge_type", "declarative"),
            emotional_sensitivity_level=getattr(lo, "emotional_sensitivity_level", "low"),
        )

    with patch("syllabus.pipeline.content.run_content_for_lesson", side_effect=make_lesson):
        result = run_content(outline, research, parsed)
    assert len(result) == 1
    assert result[0].title == "M1"
    assert len(result[0].lessons) == 1
    assert result[0].lessons[0].title == "L1"


def test_content_node_valid_state():
    from syllabus.models.schemas import Lesson, Module

    lesson_out = LessonOutline(title="L1", objective="O1")
    outline = [ModuleOutline(title="M1", objective="O1", lessons=[lesson_out])]
    research = {str(lesson_out.id): "Facts"}
    state = {
        "outline": outline,
        "research": research,
        "research_citations": {},
        "parsed_intake": ParsedIntake(
            journey_stage="x", diagnosis=None, confusion="y", level="beginner"
        ),
        "error": None,
    }
    with patch(
        "syllabus.pipeline.content.run_content",
        return_value=[
            Module(
                id=outline[0].id,
                title="M1",
                objective="O1",
                lessons=[Lesson(id=lesson_out.id, title="L1", objective="O1", blocks=[])],
            )
        ],
    ):
        result = content_node(state)
    assert result.get("error") is None
    assert len(result["modules"]) == 1
    assert result["modules"][0].title == "M1"


def test_content_node_missing_outline():
    state = {
        "outline": None,
        "research": {},
        "parsed_intake": ParsedIntake(
            journey_stage="x", diagnosis=None, confusion="y", level="beginner"
        ),
    }
    result = content_node(state)
    assert "error" in result
    assert "Missing" in result["error"]


def test_content_node_error_passthrough():
    outline = [ModuleOutline(title="M", objective="O", lessons=[])]
    state = {
        "outline": outline,
        "research": {},
        "parsed_intake": ParsedIntake(
            journey_stage="x", diagnosis=None, confusion="y", level="beginner"
        ),
        "error": "Previous error",
    }
    result = content_node(state)
    assert result == {}


def test_content_node_run_content_raises():
    lesson_out = LessonOutline(title="L1", objective="O1")
    state = {
        "outline": [ModuleOutline(title="M1", objective="O1", lessons=[lesson_out])],
        "research": {str(lesson_out.id): "Facts"},
        "parsed_intake": ParsedIntake(
            journey_stage="x", diagnosis=None, confusion="y", level="beginner"
        ),
        "error": None,
    }
    with patch(
        "syllabus.pipeline.content.run_content",
        side_effect=RuntimeError("LLM failed"),
    ):
        result = content_node(state)
    assert result.get("error") == "LLM failed"
    assert result.get("modules") is None
