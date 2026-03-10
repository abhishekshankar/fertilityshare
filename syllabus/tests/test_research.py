"""Unit tests for ResearchNode (run_research_stub, run_research, research_node)."""

from unittest.mock import patch

from syllabus.models.schemas import LessonOutline, ModuleOutline, ParsedIntake
from syllabus.pipeline.research import (
    research_node,
    run_research,
    run_research_stub,
)


def test_run_research_stub_returns_placeholder_per_lesson():
    lesson1 = LessonOutline(title="L1", objective="O1")
    lesson2 = LessonOutline(title="L2", objective="O2")
    outline = [
        ModuleOutline(title="M1", objective="O1", lessons=[lesson1]),
        ModuleOutline(title="M2", objective="O2", lessons=[lesson2]),
    ]
    facts, citations = run_research_stub(outline)
    assert isinstance(facts, dict)
    assert isinstance(citations, dict)
    assert citations == {}
    assert str(lesson1.id) in facts
    assert str(lesson2.id) in facts
    assert facts[str(lesson1.id)] == (
        "Key concepts and evidence-based points for this topic (RAG fallback)."
    )
    assert facts[str(lesson2.id)] == (
        "Key concepts and evidence-based points for this topic (RAG fallback)."
    )


def test_run_research_stub_empty_outline():
    facts, citations = run_research_stub([])
    assert facts == {}
    assert citations == {}


def test_run_research_mocked_query_facts():
    lesson1 = LessonOutline(title="IVF basics", objective="Understand protocol")
    outline = [ModuleOutline(title="M1", objective="O1", lessons=[lesson1])]
    intake_context = "Journey: Newly diagnosed. Diagnosis: PCOS."
    mock_facts = "Evidence: IVF success rates by age."
    mock_cites = [{"source": "PubMed:123", "snippet": "Abstract..."}]
    with patch("syllabus.pipeline.research.query_facts") as m:
        m.return_value = (mock_facts, mock_cites)
        research, citations = run_research(outline, intake_context)
    assert research[str(lesson1.id)] == mock_facts
    assert citations[str(lesson1.id)] == mock_cites
    m.assert_called_once()
    call_args = m.call_args
    assert "IVF basics" in call_args[0][0]
    assert call_args[1]["intake_context"] == intake_context


def test_run_research_query_facts_raises_uses_fallback():
    lesson1 = LessonOutline(title="L1", objective="O1")
    outline = [ModuleOutline(title="M1", objective="O1", lessons=[lesson1])]
    with patch("syllabus.pipeline.research.query_facts", side_effect=RuntimeError("RAG down")):
        research, citations = run_research(outline, "")
    assert research[str(lesson1.id)] == (
        "Key concepts and evidence-based points for this topic (RAG fallback)."
    )
    assert citations[str(lesson1.id)] == []


def test_research_node_valid_state():
    lesson1 = LessonOutline(title="L1", objective="O1")
    outline = [ModuleOutline(title="M1", objective="O1", lessons=[lesson1])]
    state = {
        "outline": outline,
        "parsed_intake": ParsedIntake(
            journey_stage="IVF prep",
            diagnosis="PCOS",
            confusion="Protocols",
            level="beginner",
        ),
        "error": None,
    }
    with patch("syllabus.pipeline.research.query_facts") as m:
        m.return_value = ("Facts here", [])
        result = research_node(state)
    assert result.get("error") is None
    assert "research" in result
    assert "research_citations" in result
    assert str(lesson1.id) in result["research"]
    assert result["research"][str(lesson1.id)] == "Facts here"


def test_research_node_missing_outline():
    state = {"parsed_intake": ParsedIntake(journey_stage="x", confusion="y", level="beginner")}
    result = research_node(state)
    assert result.get("error") == "Missing outline"


def test_research_node_error_passthrough():
    state = {"outline": None, "error": "Previous error"}
    result = research_node(state)
    assert result == {}


def test_research_node_run_research_raises_uses_stub():
    """When run_research raises, stub is used and error is propagated for downstream/operators."""
    lesson1 = LessonOutline(title="L1", objective="O1")
    outline = [ModuleOutline(title="M1", objective="O1", lessons=[lesson1])]
    state = {"outline": outline, "parsed_intake": None, "error": None}
    with patch("syllabus.pipeline.research.run_research", side_effect=Exception("RAG error")):
        result = research_node(state)
    assert result.get("error") == "RAG error"
    assert result["research"][str(lesson1.id)] == (
        "Key concepts and evidence-based points for this topic (RAG fallback)."
    )
    assert result["research_citations"] == {}
