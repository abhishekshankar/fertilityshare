import json
import re
from pathlib import Path

import pytest
import yaml

from syllabus.export.cog import export_cog
from syllabus.models.schemas import CourseSpec, Quiz, QuizQuestion

FIXTURE = Path(__file__).parent / "fixtures" / "course_spec_sample.json"


MODULE_RE = re.compile(r"^m\d{2}-.*\.md$")


def load_spec(per_lesson: int = 2) -> CourseSpec:
    spec = CourseSpec.model_validate(json.loads(FIXTURE.read_text()))
    for m in spec.modules:
        for lesson in m.lessons:
            lesson.quiz = Quiz(
                questions=[
                    QuizQuestion(
                        question=f"{lesson.title} q{i}?",
                        options=["A1", "B1", "C1"],
                        correct_index=i % 3,
                    )
                    for i in range(per_lesson)
                ]
            )
    return spec


def test_file_set_and_course_yml():
    spec = load_spec()
    files = export_cog(spec, "fertility-foundations")
    lesson_count = sum(len(m.lessons) for m in spec.modules)
    assert "course.yml" in files and "final-assessment.md" in files
    assert len([f for f in files if MODULE_RE.match(f)]) == lesson_count
    course = yaml.safe_load(files["course.yml"])
    assert course["slug"] == "fertility-foundations"
    assert course["status"] == "draft"
    assert course["draft_for_clinical_review"] is True
    assert course["modules"] == lesson_count
    assert "not medical advice" in course["safety_footer"]
    grouped = [n for g in course["groups"] for n in g["modules"]]
    assert grouped == list(range(1, lesson_count + 1))


def test_module_frontmatter_and_body():
    spec = load_spec()
    files = export_cog(spec, "fertility-foundations")
    first = files[sorted(f for f in files if MODULE_RE.match(f))[0]]
    front = yaml.safe_load(first.split("---")[1])
    assert front["course"] == "fertility-foundations"
    assert front["module"] == 1
    assert front["status"] == "draft"
    lesson = spec.modules[0].lessons[0]
    assert f"# Module 1: {lesson.title}" in first
    assert lesson.blocks[0].content.strip()[:40] in first


def test_rejects_empty_course():
    spec = load_spec()
    spec.modules = []
    with pytest.raises(ValueError, match=str(spec.id)):
        export_cog(spec, "x")


def test_rejects_lesson_without_blocks():
    spec = load_spec()
    bad = spec.modules[0].lessons[0]
    bad.blocks = []
    with pytest.raises(ValueError, match=rf"{spec.id}.*{bad.id}"):
        export_cog(spec, "x")


def test_final_assessment_has_six_questions():
    files = export_cog(load_spec(), "x")
    fa = files["final-assessment.md"]
    front = yaml.safe_load(fa.split("---")[1])
    assert front["pass_of"] == 6 and front["pass_need"] == 4
    assert front["max_attempts"] == 3 and front["cooldown_hours"] == 24
    assert re.findall(r"^(\d+)\. ", fa, re.M) == ["1", "2", "3", "4", "5", "6"]


def test_final_assessment_spreads_across_lessons():
    spec = load_spec()
    lessons = [le for m in spec.modules for le in m.lessons]
    fa = export_cog(spec, "x")["final-assessment.md"]
    assert f"{lessons[0].title} q0?" in fa
    if len(lessons) >= 2:
        assert f"{lessons[1].title} q0?" in fa


def test_rejects_fewer_than_six_questions():
    spec = load_spec(per_lesson=0)
    spec.modules[0].lessons[0].quiz = Quiz(
        questions=[QuizQuestion(question="q?", options=["a", "b"], correct_index=0)] * 5
    )
    with pytest.raises(ValueError, match=str(spec.id)):
        export_cog(spec, "x")


@pytest.mark.parametrize("bad", [5, -1])
def test_rejects_bad_correct_index(bad):
    spec = load_spec()
    lesson = spec.modules[0].lessons[0]
    lesson.quiz.questions[0].correct_index = bad
    with pytest.raises(ValueError, match=rf"{spec.id}.*{lesson.id}"):
        export_cog(spec, "x")


def test_rejects_empty_options():
    spec = load_spec()
    lesson = spec.modules[0].lessons[0]
    lesson.quiz.questions[0].options = []
    with pytest.raises(ValueError, match=rf"{spec.id}.*{lesson.id}"):
        export_cog(spec, "x")


def test_cli_writes_package(tmp_path):
    from typer.testing import CliRunner

    from syllabus.cli.main import app

    course_json = tmp_path / "course.json"
    course_json.write_text(load_spec().model_dump_json())
    out_dir = tmp_path / "out"
    result = CliRunner().invoke(
        app, ["export-cog", str(course_json), "fertility-foundations", str(out_dir)]
    )
    assert result.exit_code == 0, result.output
    assert (out_dir / "fertility-foundations" / "course.yml").exists()


def test_cli_exits_1_on_too_few_questions(tmp_path):
    from typer.testing import CliRunner

    from syllabus.cli.main import app

    result = CliRunner().invoke(
        app, ["export-cog", str(FIXTURE), "fertility-foundations", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "at least 6 quiz questions" in result.output
    assert not (tmp_path / "fertility-foundations").exists()


def test_platform_dialect_shapes():
    """Shapes the Cog content parser/lint require (regression: Task 5 gate failures)."""
    files = export_cog(load_spec(), "ff")
    course = files["course.yml"]
    assert re.search(r'^  - id: ff-part-1\n    title: ".+"\n    modules: \[1, 2', course, re.M)
    assert yaml.safe_load(course)["groups"][0]["modules"][0] == 1
    mod = files[sorted(f for f in files if MODULE_RE.match(f))[0]]
    front = yaml.safe_load(mod.split("---")[1])
    for key in ("competencies", "citations", "strategic_hook", "rag_anchor", "reading_level"):
        assert key in front
    assert front["competencies"] and front["strategic_hook"] is None
    assert re.search(r"\n1\.1 — .+\n", mod) and re.search(r"\n1\.2\.1 — .+\n", mod)
    assert re.search(r"\nScenario: .+\n\n.*✓ .+ Why: .+  ·  \(competency: ff\.m01\)", mod)
    fa = files["final-assessment.md"]
    assert "rag_anchor: ff-final" in fa
    assert re.findall(r"^\d+\. \(competency: ff\.m\d+\)$", fa, re.M) and fa.count("Scenario:") == 6


def test_reading_level_is_measured_not_asserted():
    from syllabus.export.cog import fk_grade

    assert fk_grade("The cat sat on the mat. The dog ran to the park.") <= 2
    hard = "Reproductive endocrinologists characteristically recommend comprehensive evaluations notwithstanding variability."
    assert fk_grade(hard) >= 15
    mod = export_cog(load_spec(), "ff")
    first = mod[sorted(f for f in mod if MODULE_RE.match(f))[0]]
    assert isinstance(yaml.safe_load(first.split("---")[1])["reading_level"], int)


def test_citations_deduplicated_preserving_order():
    from syllabus.models.schemas import Citation

    spec = load_spec()
    lesson = spec.modules[0].lessons[0]
    lesson.blocks[0].citations = [
        Citation(source="B", snippet="s"),
        Citation(source="A", snippet="s"),
        Citation(source="B", snippet="s"),
    ]
    files = export_cog(spec, "fertility-foundations")
    first = files[sorted(f for f in files if MODULE_RE.match(f))[0]]
    front = yaml.safe_load(first.split("---")[1])
    assert front["citations"][:2] == ["B", "A"]
    assert len(front["citations"]) == len(set(front["citations"]))


def test_high_sensitivity_lessons_without_quiz_emit_no_quick_check():
    spec = load_spec(per_lesson=3)
    lessons = [le for m in spec.modules for le in m.lessons]
    high = lessons[0]
    high.emotional_sensitivity_level = "high"
    high.quiz = None
    files = export_cog(spec, "x")
    first = files[sorted(f for f in files if MODULE_RE.match(f))[0]]
    assert "Quick check" not in first
    assert re.findall(r"^(\d+)\. ", files["final-assessment.md"], re.M) == list("123456")
    assert f"{high.title} q0?" not in files["final-assessment.md"]


@pytest.mark.parametrize("opts", [["only"], ["a", ""], ["a", "   "], ["A", " a "], ["a", "a"]])
def test_rejects_bad_option_sets(opts):
    spec = load_spec()
    lesson = spec.modules[0].lessons[0]
    lesson.quiz.questions[0].options = opts
    lesson.quiz.questions[0].correct_index = 0
    with pytest.raises(ValueError, match=rf"{spec.id}.*{lesson.id}"):
        export_cog(spec, "x")


def test_cli_clean_error_on_bad_course_json(tmp_path):
    from typer.testing import CliRunner

    from syllabus.cli.main import app

    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    for path in (bad, tmp_path / "missing.json"):
        result = CliRunner().invoke(app, ["export-cog", str(path), "x", str(tmp_path)])
        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "Traceback" not in result.output
        assert isinstance(result.exception, SystemExit)
