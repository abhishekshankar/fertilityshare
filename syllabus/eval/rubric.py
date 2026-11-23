"""9-dimension rubric scorer for Layer 1 A/B eval (PRD Addendum Section E.1, E.3)."""

import json
from pathlib import Path

from syllabus.models.schemas import CourseSpec
from syllabus.pipeline.qa import _has_prescriptive_language, _lesson_has_compliance_note

# E.1 dimensions: 1=Medical accuracy, 2=Structural coherence, 3=Tone, 4=Compliance,
# 5=Completeness, 6=Objective coherence, 7=Scaffolding quality, 8=Knowledge topology fit,
# 9=Emotional calibration
DIMENSION_NAMES = [
    "medical_accuracy",
    "structural_coherence",
    "tone",
    "compliance",
    "completeness",
    "objective_coherence",
    "scaffolding_quality",
    "knowledge_topology_fit",
    "emotional_calibration",
]


def _dim1_medical_accuracy(spec: CourseSpec) -> tuple[bool, str]:
    """Facts correct; no prescriptive advice. Use rule-based check only."""
    for mod in spec.modules:
        for lesson in mod.lessons:
            for b in lesson.blocks:
                if _has_prescriptive_language(b.content):
                    return False, f"Lesson '{lesson.title}' block contains prescriptive language"
    return True, "OK"


def _dim4_compliance(spec: CourseSpec) -> tuple[bool, str]:
    """Every lesson has compliance_note block."""
    for mod in spec.modules:
        for lesson in mod.lessons:
            if not _lesson_has_compliance_note(lesson):
                return False, f"Lesson '{lesson.title}' missing compliance_note or RE question"
    return True, "OK"


def _dim6_objective_coherence_heuristic(spec: CourseSpec) -> tuple[bool, str]:
    """Objective coherence: Layer 1 injects target_end_state; presence signals objective-driven arc."""
    end_state = getattr(spec.intake, "target_end_state", None) or ""
    if not isinstance(end_state, str):
        end_state = ""
    if end_state.strip():
        return True, "OK (target_end_state present; full coherence requires human review)"
    return False, "Missing target_end_state (pre-Layer 1 or IntentNode did not set objective)"


def _dim7_scaffolding_heuristic(spec: CourseSpec) -> tuple[bool, str]:
    """Backward arc; scope compression; one-concept-per-lesson; max 4 modules."""
    if len(spec.modules) > 4:
        return False, f"More than 4 modules ({len(spec.modules)})"
    total_lessons = sum(len(m.lessons) for m in spec.modules)
    if total_lessons > 20:
        return False, f"Too many lessons ({total_lessons}); scope not compressed"
    return True, "OK"


def _dim9_emotional_calibration_heuristic(spec: CourseSpec) -> tuple[bool, str]:
    """No quiz after high emotional_sensitivity content; supportive closure.
    When Lesson has emotional_sensitivity_level or blocks have it, we can check.
    For now: if any lesson has quiz and title/objective suggest emotional (failed, grief),
    flag for human review. We pass if no quiz present (V0 often has no quiz)."""
    # Once we have emotional_sensitivity_level on lessons, fail if quiz present on high-sensitivity lesson
    for mod in spec.modules:
        for lesson in mod.lessons:
            if lesson.quiz and getattr(lesson, "emotional_sensitivity_level", None) == "high":
                return (
                    False,
                    f"Lesson '{lesson.title}' has quiz but emotional_sensitivity_level=high",
                )
    return True, "OK"


def score_course_spec(spec: CourseSpec) -> dict:
    """
    Score a CourseSpec on the 9-dimension rubric (E.1).
    Returns a dict: { "dimensions": { "1": {"pass": bool, "note": str}, ... }, "overall_pass": bool }.
    Dimensions 1, 4, 6, 7, 9 have automated checks; 2, 3, 5, 8 are human_review.
    """
    results = {}
    # Automated
    pass1, note1 = _dim1_medical_accuracy(spec)
    results["1"] = {"pass": pass1, "note": note1, "dimension": "medical_accuracy"}
    pass4, note4 = _dim4_compliance(spec)
    results["4"] = {"pass": pass4, "note": note4, "dimension": "compliance"}
    pass6, note6 = _dim6_objective_coherence_heuristic(spec)
    results["6"] = {"pass": pass6, "note": note6, "dimension": "objective_coherence"}
    pass7, note7 = _dim7_scaffolding_heuristic(spec)
    results["7"] = {"pass": pass7, "note": note7, "dimension": "scaffolding_quality"}
    pass9, note9 = _dim9_emotional_calibration_heuristic(spec)
    results["9"] = {"pass": pass9, "note": note9, "dimension": "emotional_calibration"}
    # Human review placeholders (2, 3, 5, 8)
    for dim, name in [
        (2, "structural_coherence"),
        (3, "tone"),
        (5, "completeness"),
        (8, "knowledge_topology_fit"),
    ]:
        if str(dim) not in results:
            results[str(dim)] = {"pass": None, "note": "human_review", "dimension": name}
    overall = all(results[str(d)].get("pass") is not False for d in range(1, 10))
    return {"dimensions": results, "overall_pass": overall, "automated_only": True}


def score_course_file(path: Path) -> dict | None:
    """Load CourseSpec from JSON and return score dict or None on error."""
    try:
        with open(path) as f:
            data = json.load(f)
        spec = CourseSpec.model_validate(data)
        out = score_course_spec(spec)
        out["course_file"] = str(path)
        return out
    except Exception as e:
        return {"error": str(e), "course_file": str(path), "dimensions": {}, "overall_pass": False}


def score_directory(out_dir: str | Path, pattern: str = "course_*.json") -> dict:
    """
    Score all course_01.json .. course_10.json in out_dir.
    Returns { "courses": [ { "file", "score" } ], "summary": { "passed": int, "total": int, "by_dimension": {...} } }
    """
    out_path = Path(out_dir)
    if not out_path.is_dir():
        return {"error": f"Not a directory: {out_dir}", "courses": [], "summary": {}}
    files = sorted(out_path.glob(pattern))
    courses = []
    by_dimension: dict[str, list[bool | None]] = {str(d): [] for d in range(1, 10)}
    for f in files:
        s = score_course_file(f)
        if s is None:
            continue
        if "error" in s:
            courses.append({"file": f.name, "error": s["error"], "score": None})
            continue
        courses.append({"file": f.name, "score": s})
        for d in range(1, 10):
            by_dimension[str(d)].append(s["dimensions"].get(str(d), {}).get("pass"))
    total = len(courses)
    passed_all = sum(1 for c in courses if c.get("score", {}).get("overall_pass"))
    summary = {
        "total": total,
        "passed_automated_plus_hr": passed_all,
        "by_dimension": {
            d: {
                "pass_count": sum(1 for v in by_dimension[d] if v is True),
                "fail_count": sum(1 for v in by_dimension[d] if v is False),
                "human_review_count": sum(1 for v in by_dimension[d] if v is None),
            }
            for d in by_dimension
        },
    }
    return {"courses": courses, "summary": summary}
