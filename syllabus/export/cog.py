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


def _module_md(course_slug: str, n: int, lesson: Lesson) -> str:
    front = {
        "id": f"{course_slug}-m{n:02d}",
        "title": lesson.title,
        "course": course_slug,
        "module": n,
        "version": "1.0.0",
        "status": "draft",
        "citations": [c.source for b in lesson.blocks for c in b.citations if c.source],
    }
    parts = [
        f"---\n{yaml.safe_dump(front, sort_keys=False)}---",
        f"# Module {n}: {lesson.title}",
        lesson.objective,
    ]
    if lesson.key_takeaways:
        parts.append("## Key takeaways\n" + "\n".join(f"- {t}" for t in lesson.key_takeaways))
    parts += [b.content.strip() for b in lesson.blocks]
    if lesson.quiz and lesson.quiz.questions:
        qs = []
        for i, q in enumerate(lesson.quiz.questions, 1):
            opts = "\n".join(f"   {chr(97 + j)}. {o}" for j, o in enumerate(q.options))
            qs.append(f"{i}. {q.question}\n{opts}\n   Answer: {chr(97 + q.correct_index)}")
        parts.append("## Quick check\n" + "\n".join(qs))
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

    per_lesson = [lesson.quiz.questions if lesson.quiz else [] for _, lesson in lessons]
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

    body = "\n".join(
        f"{i}. {q.question}\n"
        + "\n".join(f"   {chr(97 + j)}. {o}" for j, o in enumerate(q.options))
        + f"\n   Answer: {chr(97 + q.correct_index)}"
        for i, q in enumerate(questions, 1)
    )
    assessment_front = {
        "id": f"{slug}-final",
        "title": "Final Assessment",
        "course": slug,
        "version": "1.0.0",
        "status": "draft",
        "pass_of": 6,
        "pass_need": 4,
    }
    files["final-assessment.md"] = (
        f"---\n{yaml.safe_dump(assessment_front, sort_keys=False)}---\n\n"
        f"# Final Assessment\n\n{body}\n"
    )
    files["course.yml"] = yaml.safe_dump(
        {
            "id": slug,
            "title": spec.title,
            "slug": slug,
            "tier": 0,
            "modules": n,
            "version": "1.0.0",
            "status": "draft",
            "draft_for_clinical_review": True,
            "safety_footer": SAFETY_FOOTER,
            "groups": groups,
            "summary": spec.intake.target_end_state or spec.title,
        },
        sort_keys=False,
    )
    return files
