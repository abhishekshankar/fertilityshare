"""Tests for 9-dimension rubric scorer (Layer 1 eval, PRD Addendum E.1/E.3)."""

from syllabus.models.schemas import (
    ContentBlock,
    ContentBlockType,
    CourseSpec,
    IntakeData,
    Lesson,
    Metadata,
    Module,
)
from syllabus.eval.rubric import score_course_spec, score_course_file, score_directory
from pathlib import Path
import tempfile
import json


def _minimal_course_spec(blocks_per_lesson=None):
    blocks_per_lesson = blocks_per_lesson or [
        ContentBlock(type=ContentBlockType.explanation, content="Factual content."),
        ContentBlock(
            type=ContentBlockType.compliance_note,
            content="Ask your RE: What options do I have?",
        ),
    ]
    lesson = Lesson(
        title="L1",
        objective="Learn X",
        blocks=blocks_per_lesson,
    )
    mod = Module(title="M1", objective="O1", lessons=[lesson])
    return CourseSpec(
        title="Test",
        intake=IntakeData(
            journey_stage="x",
            diagnosis=None,
            confusion="y",
            level="beginner",
            target_end_state="By the end you will understand X.",
        ),
        modules=[mod],
        metadata=Metadata(),
    )


def test_score_course_spec_pass():
    spec = _minimal_course_spec()
    result = score_course_spec(spec)
    assert "dimensions" in result
    assert result["dimensions"]["1"]["pass"] is True
    assert result["dimensions"]["4"]["pass"] is True
    assert result["dimensions"]["6"]["pass"] is True
    assert result["dimensions"]["7"]["pass"] is True
    assert result["overall_pass"] is True


def test_score_course_spec_fail_dim6_missing_target_end_state():
    """Dim 6 (objective coherence) fails when target_end_state is missing (pre-Layer 1)."""
    spec = _minimal_course_spec()
    spec.intake.target_end_state = ""
    result = score_course_spec(spec)
    assert result["dimensions"]["6"]["pass"] is False
    assert "target_end_state" in result["dimensions"]["6"]["note"].lower()


def test_score_course_spec_fail_prescriptive():
    blocks = [
        ContentBlock(type=ContentBlockType.explanation, content="You should take 50 mg daily."),
        ContentBlock(
            type=ContentBlockType.compliance_note,
            content="Ask your RE.",
        ),
    ]
    spec = _minimal_course_spec(blocks_per_lesson=blocks)
    result = score_course_spec(spec)
    assert result["dimensions"]["1"]["pass"] is False
    assert "prescriptive" in result["dimensions"]["1"]["note"].lower()


def test_score_course_spec_fail_compliance():
    blocks = [
        ContentBlock(type=ContentBlockType.explanation, content="Only block."),
    ]
    spec = _minimal_course_spec(blocks_per_lesson=blocks)
    result = score_course_spec(spec)
    assert result["dimensions"]["4"]["pass"] is False


def test_score_course_file(tmp_path):
    spec = _minimal_course_spec()
    path = tmp_path / "course_01.json"
    with open(path, "w") as f:
        json.dump(spec.model_dump(mode="json"), f, indent=2)
    result = score_course_file(path)
    assert result is not None
    assert "error" not in result
    assert result["overall_pass"] is True


def test_score_directory_empty(tmp_path):
    result = score_directory(tmp_path)
    assert result["summary"]["total"] == 0
    assert "error" not in result


def test_score_directory_with_files(tmp_path):
    spec = _minimal_course_spec()
    for i in range(2):
        path = tmp_path / f"course_{i + 1:02d}.json"
        with open(path, "w") as f:
            json.dump(spec.model_dump(mode="json"), f, indent=2)
    result = score_directory(tmp_path)
    assert result["summary"]["total"] == 2
    assert result["summary"]["passed_automated_plus_hr"] == 2
    assert len(result["courses"]) == 2
