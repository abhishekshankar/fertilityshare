"""Unit tests for OutlineNode (parse, run_outline, outline_node)."""

from unittest.mock import MagicMock, patch

from syllabus.models.schemas import LessonOutline, ModuleOutline, ParsedIntake
from syllabus.pipeline.outline import (
    _parse_outline_response,
    outline_node,
    run_outline,
)


def test_parse_outline_response_well_formed():
    content = """{"modules": [
        {"title": "Module 1", "objective": "Learn basics", "lessons": [
            {"title": "Lesson 1", "objective": "Understand X"},
            {"title": "Lesson 2", "objective": "Understand Y"}
        ]},
        {"title": "Module 2", "objective": "Go deeper", "lessons": [
            {"title": "Lesson 3", "objective": "Apply X"}
        ]}
    ]}"""
    result = _parse_outline_response(content)
    assert len(result) == 2
    assert result[0].title == "Module 1"
    assert result[0].objective == "Learn basics"
    assert len(result[0].lessons) == 2
    assert result[0].lessons[0].title == "Lesson 1"
    assert result[0].lessons[0].objective == "Understand X"
    assert result[1].title == "Module 2"
    assert len(result[1].lessons) == 1


def test_parse_outline_response_with_markdown_code_block():
    content = """Some text
```json
{"modules": [{"title": "M1", "objective": "O1", "lessons": [{"title": "L1", "objective": "O1"}]}]}
```
"""
    result = _parse_outline_response(content)
    assert len(result) == 1
    assert result[0].title == "M1"
    assert result[0].lessons[0].title == "L1"


def test_parse_outline_response_empty_modules():
    content = '{"modules": []}'
    result = _parse_outline_response(content)
    assert result == []


def test_parse_outline_response_missing_lesson_fields_default_empty():
    content = '{"modules": [{"title": "M1", "lessons": [{"title": "L1"}]}]}'
    result = _parse_outline_response(content)
    assert len(result) == 1
    assert result[0].lessons[0].title == "L1"
    assert result[0].lessons[0].objective == ""
    assert result[0].lessons[0].knowledge_type == "declarative"


def test_parse_outline_response_includes_knowledge_type():
    content = """{"modules": [{"title": "M1", "objective": "O1", "lessons": [
        {"title": "L1", "objective": "O1", "knowledge_type": "procedural"},
        {"title": "L2", "objective": "O2", "knowledge_type": "conditional"}
    ]}]}"""
    result = _parse_outline_response(content)
    assert result[0].lessons[0].knowledge_type == "procedural"
    assert result[0].lessons[1].knowledge_type == "conditional"
    assert result[0].lessons[0].emotional_sensitivity_level == "low"
    assert result[0].lessons[1].emotional_sensitivity_level == "low"


def test_parse_outline_response_includes_emotional_sensitivity_level():
    content = """{"modules": [{"title": "M1", "objective": "O1", "lessons": [
        {"title": "L1", "objective": "O1", "emotional_sensitivity_level": "high"},
        {"title": "L2", "objective": "O2", "emotional_sensitivity_level": "medium"}
    ]}]}"""
    result = _parse_outline_response(content)
    assert result[0].lessons[0].emotional_sensitivity_level == "high"
    assert result[0].lessons[1].emotional_sensitivity_level == "medium"


def test_run_outline_mocked_llm():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = """{"modules": [
        {"title": "Intro", "objective": "Start", "lessons": [
            {"title": "Welcome", "objective": "Get oriented"}
        ]}
    ]}"""
    parsed = ParsedIntake(
        journey_stage="Newly diagnosed",
        diagnosis="PCOS",
        confusion="What is AMH?",
        level="beginner",
    )
    result = run_outline(parsed, llm=mock_llm)
    assert isinstance(result, list)
    assert all(isinstance(m, ModuleOutline) for m in result)
    assert len(result) == 1
    assert result[0].title == "Intro"
    assert len(result[0].lessons) == 1
    assert result[0].lessons[0].title == "Welcome"
    mock_llm.invoke.assert_called_once()


def test_outline_node_valid_state():
    state = {
        "parsed_intake": ParsedIntake(
            journey_stage="IVF prep",
            diagnosis=None,
            confusion="Protocols",
            level="intermediate",
        ),
        "error": None,
    }
    with patch(
        "syllabus.pipeline.outline.run_outline",
        return_value=[
            ModuleOutline(
                title="M1",
                objective="O1",
                lessons=[LessonOutline(title="L1", objective="Obj1")],
            )
        ],
    ):
        result = outline_node(state)
    assert result.get("error") is None
    assert "outline" in result
    assert len(result["outline"]) == 1
    assert result["outline"][0].title == "M1"


def test_outline_node_parsed_intake_as_dict():
    state = {
        "parsed_intake": {
            "journey_stage": "Egg freezing",
            "diagnosis": None,
            "confusion": "Cost",
            "level": "beginner",
        },
        "error": None,
    }
    with patch(
        "syllabus.pipeline.outline.run_outline",
        return_value=[ModuleOutline(title="M", objective="O", lessons=[])],
    ):
        result = outline_node(state)
    assert result.get("error") is None
    assert result.get("outline") is not None


def test_outline_node_missing_parsed_intake():
    state = {"raw_intake": "something", "error": None}
    result = outline_node(state)
    assert result.get("error") == "Missing parsed_intake"
    assert "outline" not in result or result.get("outline") is None


def test_outline_node_error_passthrough():
    state = {"parsed_intake": None, "error": "Previous error"}
    result = outline_node(state)
    assert result == {}


def test_outline_node_run_outline_raises():
    state = {
        "parsed_intake": ParsedIntake(
            journey_stage="x", diagnosis=None, confusion="y", level="beginner"
        ),
        "error": None,
    }
    with patch(
        "syllabus.pipeline.outline.run_outline",
        side_effect=ValueError("LLM failed"),
    ):
        result = outline_node(state)
    assert result.get("error") == "LLM failed"
    assert result.get("outline") is None
