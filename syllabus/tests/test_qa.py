"""Unit tests for QANode: compliance_note and prescriptive language (PRD T-005)."""

from uuid import uuid4

from syllabus.models.schemas import (
    ContentBlock,
    ContentBlockType,
    CourseSpec,
    IntakeData,
    Lesson,
    Module,
)
from syllabus.pipeline.qa import (
    _has_prescriptive_language,
    _lesson_has_compliance_note,
    _lesson_has_no_prescriptive,
    run_qa_rules,
)


def test_has_prescriptive_language_detects_dosage():
    assert _has_prescriptive_language("You should take 150mg of clomid") is True
    assert _has_prescriptive_language("Start with 100 mg") is True
    assert _has_prescriptive_language("Talk to your doctor about options") is False


def test_lesson_has_compliance_note():
    yes = Lesson(
        title="Test",
        objective="Test",
        blocks=[
            ContentBlock(type=ContentBlockType.explanation, content="Body"),
            ContentBlock(type=ContentBlockType.compliance_note, content="Ask your RE: What next?"),
        ],
    )
    assert _lesson_has_compliance_note(yes) is True
    no = Lesson(
        title="Test",
        objective="Test",
        blocks=[ContentBlock(type=ContentBlockType.explanation, content="Only")],
    )
    assert _lesson_has_compliance_note(no) is False


def test_lesson_has_no_prescriptive():
    clean = Lesson(
        title="Test",
        objective="Test",
        blocks=[ContentBlock(type=ContentBlockType.explanation, content="Education only.")],
    )
    assert _lesson_has_no_prescriptive(clean) is True
    bad = Lesson(
        title="Test",
        objective="Test",
        blocks=[ContentBlock(type=ContentBlockType.explanation, content="You should take 150mg.")],
    )
    assert _lesson_has_no_prescriptive(bad) is False


def test_run_qa_rules_pass():
    lesson = Lesson(
        title="L1",
        objective="O1",
        blocks=[
            ContentBlock(type=ContentBlockType.explanation, content="Info."),
            ContentBlock(type=ContentBlockType.compliance_note, content="Ask your RE: What to do?"),
        ],
    )
    mod = Module(id=uuid4(), title="M1", objective="O1", lessons=[lesson])
    spec = CourseSpec(
        title="Course",
        intake=IntakeData(journey_stage="x", confusion="y", level="beginner"),
        modules=[mod],
    )
    passed, msg = run_qa_rules(spec)
    assert passed is True
    assert msg == "OK"


def test_run_qa_rules_fail_missing_compliance():
    lesson = Lesson(
        title="L1",
        objective="O1",
        blocks=[ContentBlock(type=ContentBlockType.explanation, content="Only body.")],
    )
    mod = Module(id=uuid4(), title="M1", objective="O1", lessons=[lesson])
    spec = CourseSpec(
        title="Course",
        intake=IntakeData(journey_stage="x", confusion="y", level="beginner"),
        modules=[mod],
    )
    passed, msg = run_qa_rules(spec)
    assert passed is False
    assert "compliance" in msg.lower() or "L1" in msg


def test_run_qa_rules_fail_prescriptive():
    lesson = Lesson(
        title="L1",
        objective="O1",
        blocks=[
            ContentBlock(type=ContentBlockType.explanation, content="You should take 150mg."),
            ContentBlock(type=ContentBlockType.compliance_note, content="Ask your RE."),
        ],
    )
    mod = Module(id=uuid4(), title="M1", objective="O1", lessons=[lesson])
    spec = CourseSpec(
        title="Course",
        intake=IntakeData(journey_stage="x", confusion="y", level="beginner"),
        modules=[mod],
    )
    passed, msg = run_qa_rules(spec)
    assert passed is False
    assert "prescriptive" in msg.lower() or "L1" in msg


def test_qa_node_catches_injected_prescriptive():
    """Compliance test: 100% catch rate for injected prescriptive language (PRD 8.1)."""
    from syllabus.pipeline.qa import qa_node

    lesson = Lesson(
        title="Bad",
        objective="O",
        blocks=[
            ContentBlock(type=ContentBlockType.explanation, content="Take 200mg daily."),
            ContentBlock(type=ContentBlockType.compliance_note, content="Ask your RE."),
        ],
    )
    mod = Module(id=uuid4(), title="M", objective="O", lessons=[lesson])
    state = {
        "parsed_intake": {"journey_stage": "x", "confusion": "y", "level": "beginner"},
        "modules": [mod],
        "error": None,
    }
    result = qa_node(state)
    assert result.get("qa_passed") is False
    assert result.get("course_spec") is None
    assert result.get("error")
