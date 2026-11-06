import json
import re
from itertools import zip_longest

import yaml

from syllabus.models.schemas import CourseSpec, Lesson

SAFETY_FOOTER = (
    "Educational content only; not medical advice. Talk to a qualified "
    "fertility clinician about your situation."
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


BLOCK_LABEL = {
    "explanation": "Explanation",
    "example": "Example",
    "exercise": "Try it",
    "reflection": "Reflect",
    "compliance_note": "A note on safety",
}


def _competency(course_slug: str, n: int) -> str:
    return f"{course_slug}.m{n:02d}"


def _options_line(q, why: str, tail: str = "") -> str:
    # Cog dialect: "A  ·  - B  ·  - ✓ C Why: ..." on one line.
    opts = [("✓ " if j == q.correct_index else "") + o for j, o in enumerate(q.options)]
    opts[q.correct_index] += f" Why: {why}{tail}"
    return "  ·  - ".join(opts)


def _why(q) -> str:
    return (q.explanation or "").strip() or f"The correct answer is: {q.options[q.correct_index]}"


def _syllables(word: str) -> int:
    groups = re.findall(r"[aeiouy]+", word.lower())
    n = len(groups) - (1 if word.lower().endswith("e") and len(groups) > 1 else 0)
    return max(1, n)


def fk_grade(text: str) -> int:
    """Flesch-Kincaid grade (rounded, >= 0). ponytail: vowel-group syllable heuristic, ~1 grade error."""
    words = re.findall(r"[A-Za-z']+", text)
    sentences = max(1, len(re.findall(r"[.!?]+(?:\s|$)", text)))
    if not words:
        return 0
    syl = sum(_syllables(w) for w in words)
    return max(0, round(0.39 * len(words) / sentences + 11.8 * syl / len(words) - 15.59))


def _module_md(course_slug: str, n: int, lesson: Lesson) -> str:
    body = " ".join(b.content for b in lesson.blocks)
    front = {
        "id": f"{course_slug}-m{n:02d}",
        "title": lesson.title,
        "course": course_slug,
        "module": n,
        "version": "1.0.0",
        "status": "draft",
        "competencies": [_competency(course_slug, n)],
        "citations": list(
            dict.fromkeys(c.source for b in lesson.blocks for c in b.citations if c.source)
        ),
        "strategic_hook": None,
        "rag_anchor": f"{course_slug}-m{n:02d}",
        "reading_level": fk_grade(body),  # measured, not the target
    }
    learn = [lesson.objective.strip(), *[t.strip() for t in lesson.key_takeaways]]
    parts = [
        f"---\n{yaml.safe_dump(front, sort_keys=False)}---",
        f"# Module {n}: {lesson.title}",
        f"{n}.1 — Overview",
        f"{n}.1.1 — What you will learn",
        *learn,
        f"{n}.2 — {lesson.title}",
    ]
    for i, b in enumerate(lesson.blocks, 1):
        parts.append(f"{n}.2.{i} — {BLOCK_LABEL.get(b.type, b.type.replace('_', ' ').title())}")
        parts += [ln.strip() for ln in b.content.strip().splitlines() if ln.strip()]
    if lesson.quiz and lesson.quiz.questions:
        parts.append("Quick check")
        for q in lesson.quiz.questions:
            parts.append(f"Scenario: {q.question}")
            tail = f"  ·  (competency: {_competency(course_slug, n)})"
            parts.append(_options_line(q, _why(q), tail))
    return "\n\n".join(parts) + "\n"


def export_cog(spec: CourseSpec, slug: str) -> dict[str, str]:
    lessons = [(m, lesson) for m in spec.modules for lesson in m.lessons]
    if not lessons:
        raise ValueError(f"course {spec.id} has no lessons")
    for _, lesson in lessons:
        if not lesson.title.strip() or not lesson.blocks:
            raise ValueError(f"lesson {lesson.id} needs a title and blocks")
        for q in lesson.quiz.questions if lesson.quiz else []:
            if not q.options or not 0 <= q.correct_index < len(q.options):
                raise ValueError(f"lesson {lesson.id} has a quiz question with invalid answer")

    per_lesson = [
        [(i, q) for q in (lesson.quiz.questions if lesson.quiz else [])]
        for i, (_, lesson) in enumerate(lessons, 1)
    ]
    questions = [q for row in zip_longest(*per_lesson) for q in row if q is not None]
    if len(questions) < 6:
        raise ValueError(
            f"course {spec.id} needs at least 6 quiz questions for the final assessment"
        )
    questions = questions[:6]

    files: dict[str, str] = {}
    groups, n = [], 0
    for mi, module in enumerate(spec.modules):
        nums = []
        for lesson in module.lessons:
            n += 1
            nums.append(n)
            files[f"m{n:02d}-{_slug(lesson.title) or 'lesson'}.md"] = _module_md(slug, n, lesson)
        if nums:
            groups.append({"id": f"{slug}-part-{mi + 1}", "title": module.title, "modules": nums})

    body = "\n\n".join(
        f"{i}. (competency: {_competency(slug, ln)})\n\nScenario: {q.question}\n\n"
        + _options_line(q, _why(q))
        for i, (ln, q) in enumerate(questions, 1)
    )
    assessment_front = {
        "id": f"{slug}-final",
        "title": "Final Assessment",
        "course": slug,
        "version": "1.0.0",
        "status": "draft",
        "pass_of": 6,
        "pass_need": 4,
        "rag_anchor": f"{slug}-final",
    }
    files["final-assessment.md"] = (
        f"---\n{yaml.safe_dump(assessment_front, sort_keys=False)}---\n\n"
        f"# Final Assessment\n\n{body}\n"
    )
    # Hand-written (not yaml.dump): the platform's course.yml parser is line-based and
    # needs inline `modules: [..]`, quoted titles, and single-line scalars.
    q = lambda v: json.dumps(str(v), ensure_ascii=False)  # noqa: E731
    group_yml = "".join(
        f"  - id: {g['id']}\n    title: {q(g['title'])}\n    modules: {g['modules']}\n"
        for g in groups
    )
    files["course.yml"] = (
        f"id: {slug}\ntitle: {q(spec.title)}\nslug: {slug}\ntier: 0\nmodules: {n}\n"
        f"version: 1.0.0\nstatus: draft\ndraft_for_clinical_review: true\n"
        f"safety_footer: {q(SAFETY_FOOTER)}\n\ngroups:\n{group_yml}\n"
        f"summary: {q(spec.intake.target_end_state or spec.title)}\n"
    )
    return files
