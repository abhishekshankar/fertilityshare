"""Unit tests for IntentNode (sanitization, dict parsing)."""

from syllabus.models.schemas import ParsedIntake
from syllabus.pipeline.intent import _parse_from_dict, _sanitize, run_intent


def test_sanitize_truncates_and_strips():
    assert _sanitize("  a  b  ") == "a b"
    assert len(_sanitize("x" * 3000, max_len=100)) == 100


def test_sanitize_removes_control_chars():
    out = _sanitize("hello\x00world\x1f")
    assert "\x00" not in out and "\x1f" not in out


def test_parse_from_dict():
    d = {
        "journey_stage": "Preparing for first IVF",
        "diagnosis": "PCOS",
        "confusion": "I don't understand stim protocols",
        "level": "beginner",
    }
    p = _parse_from_dict(d)
    assert isinstance(p, ParsedIntake)
    assert p.journey_stage == "Preparing for first IVF"
    assert p.diagnosis == "PCOS"
    assert p.confusion == "I don't understand stim protocols"
    assert p.level == "beginner"


def test_parse_from_dict_normalizes_level():
    p = _parse_from_dict({"journey_stage": "x", "confusion": "y", "level": "INTERMEDIATE"})
    assert p.level == "intermediate"


def test_parse_from_dict_missing_level_defaults_beginner():
    p = _parse_from_dict({"journey_stage": "x", "confusion": "y"})
    assert p.level == "beginner"


def test_run_intent_with_dict():
    out = run_intent(
        {
            "journey_stage": "Newly diagnosed",
            "diagnosis": None,
            "confusion": "What does AMH mean?",
            "level": "beginner",
        }
    )
    assert out.journey_stage == "Newly diagnosed"
    assert out.diagnosis is None
    assert out.confusion == "What does AMH mean?"


def test_intent_node_with_dict_state():
    from syllabus.pipeline.intent import intent_node

    state = {
        "raw_intake": {"journey_stage": "Egg freezing", "confusion": "cost?", "level": "beginner"}
    }
    result = intent_node(state)
    assert "error" in result
    assert result.get("error") is None
    assert result.get("parsed_intake") is not None
    assert result["parsed_intake"].journey_stage == "Egg freezing"


def test_intent_node_missing_raw_intake():
    from syllabus.pipeline.intent import intent_node

    result = intent_node({})
    assert result.get("error") == "Missing raw_intake"
