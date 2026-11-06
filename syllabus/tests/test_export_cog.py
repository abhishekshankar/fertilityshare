import json
from pathlib import Path

import pytest
import yaml

from syllabus.export.cog import export_cog
from syllabus.models.schemas import CourseSpec

FIXTURE = Path(__file__).resolve().parents[2] / "out" / "course_01.json"


def load_spec() -> CourseSpec:
    return CourseSpec.model_validate(json.loads(FIXTURE.read_text()))


def test_file_set_and_course_yml():
    spec = load_spec()
    files = export_cog(spec, "fertility-foundations")
    lesson_count = sum(len(m.lessons) for m in spec.modules)
    assert "course.yml" in files and "final-assessment.md" in files
    assert len([f for f in files if f.startswith("m")]) == lesson_count
    course = yaml.safe_load(files["course.yml"])
    assert course["slug"] == "fertility-foundations"
    assert course["status"] == "draft"
    assert course["draft_for_clinical_review"] is True
    assert course["modules"] == lesson_count
    grouped = [n for g in course["groups"] for n in g["modules"]]
    assert grouped == list(range(1, lesson_count + 1))


def test_module_frontmatter_and_body():
    spec = load_spec()
    files = export_cog(spec, "fertility-foundations")
    first = files[sorted(f for f in files if f.startswith("m"))[0]]
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
    with pytest.raises(ValueError, match=str(bad.id)):
        export_cog(spec, "x")
