# FertilityShare Learn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship learn.fertilityshare.com on a copy of the Cogtraining engine, fed by courses that Syllabus generates and exports in Cogtraining's format.

**Architecture:** Syllabus becomes CLI-only. A pure `export_cog` function turns a `CourseSpec` into a Cogtraining course package (`course.yml` + module markdown files + `final-assessment.md`). A new `fertilityshare-learn` repo, copied from `cogtraining` and rebranded, imports those packages behind its existing lint and clinical-review gates.

**Tech Stack:** Python 3.11, Pydantic, Typer, PyYAML (Syllabus). Next.js 16 on Cloudflare Workers, Neon, pnpm/Turborepo (learn repo, inherited from cogtraining).

Spec: `docs/superpowers/specs/2026-11-06-fertilityshare-learn-design.md`

## Global Constraints

- Every exported course has `status: draft` and `draft_for_clinical_review: true`. Nothing publishes without a named clinician's sign-off.
- Shared catalog only: no per-learner generated courses.
- Flashcards are not exported.
- Final assessment pass mark: 4 of 6.
- cogtraining.org and the `cogtraining` repo are not modified.
- Safety footer: "Educational content only; not medical advice. Talk to a qualified fertility clinician about your situation."
- Repos live in iCloud-synced `~/Documents/GitHub`, so avoid repo-wide `grep -r`. Use `git grep` or targeted paths.

---

### Task 1: `export_cog` converter

**Files:**
- Create: `syllabus/export/__init__.py` (empty)
- Create: `syllabus/export/cog.py`
- Test: `syllabus/tests/test_export_cog.py`

**Interfaces:**
- Produces: `export_cog(spec: CourseSpec, slug: str) -> dict[str, str]`, a mapping from relative file path to file text. Raises `ValueError` naming the course or lesson id on invalid input.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `pytest syllabus/tests/test_export_cog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'syllabus.export'`

- [ ] **Step 3: Implement**

```python
import re

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
    parts = [f"---\n{yaml.safe_dump(front, sort_keys=False)}---", f"# Module {n}: {lesson.title}", lesson.objective]
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
    lessons = [(m, l) for m in spec.modules for l in m.lessons]
    if not lessons:
        raise ValueError(f"course {spec.id} has no lessons")
    for _, l in lessons:
        if not l.title.strip() or not l.blocks:
            raise ValueError(f"lesson {l.id} needs a title and blocks")

    files: dict[str, str] = {}
    groups, n = [], 0
    for mi, module in enumerate(spec.modules):
        nums = []
        for lesson in module.lessons:
            n += 1
            nums.append(n)
            files[f"m{n:02d}-{_slug(lesson.title)}.md"] = _module_md(slug, n, lesson)
        if nums:
            groups.append({"id": f"{slug}-part-{mi + 1}", "title": module.title, "modules": nums})

    questions = [q for _, l in lessons if l.quiz for q in l.quiz.questions][:6]
    body = "\n".join(
        f"{i}. {q.question}\n" + "\n".join(f"   {chr(97 + j)}. {o}" for j, o in enumerate(q.options))
        + f"\n   Answer: {chr(97 + q.correct_index)}"
        for i, q in enumerate(questions, 1)
    )
    files["final-assessment.md"] = (
        f"---\n{yaml.safe_dump({'id': f'{slug}-final', 'title': 'Final Assessment', 'course': slug, 'version': '1.0.0', 'status': 'draft', 'pass_of': 6, 'pass_need': 4}, sort_keys=False)}---\n\n# Final Assessment\n\n{body}\n"
    )
    files["course.yml"] = yaml.safe_dump(
        {
            "id": slug, "title": spec.title, "slug": slug, "tier": 0,
            "modules": n, "version": "1.0.0", "status": "draft",
            "draft_for_clinical_review": True, "safety_footer": SAFETY_FOOTER,
            "groups": groups, "summary": spec.intake.target_end_state or spec.title,
        },
        sort_keys=False,
    )
    return files
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `pytest syllabus/tests/test_export_cog.py -v`
Expected: 4 passed. If `yaml` is missing, add `"pyyaml>=6.0"` to `dependencies` in `pyproject.toml` and run `pip install -e ".[dev]"`.

- [ ] **Step 5: Commit**

```bash
git add syllabus/export syllabus/tests/test_export_cog.py pyproject.toml
git commit -m "feat: export CourseSpec to Cogtraining course package"
```

---

### Task 2: `export-cog` CLI command

**Files:**
- Modify: `syllabus/cli/main.py` (add a command after the existing ones)
- Test: `syllabus/tests/test_export_cog.py` (append)

**Interfaces:**
- Consumes: `export_cog(spec, slug) -> dict[str, str]` from Task 1
- Produces: `python -m syllabus export-cog <course.json> <slug> <out_dir>`

- [ ] **Step 1: Write the failing test**

```python
from typer.testing import CliRunner

from syllabus.cli.main import app


def test_cli_writes_package(tmp_path):
    result = CliRunner().invoke(app, ["export-cog", str(FIXTURE), "fertility-foundations", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "fertility-foundations" / "course.yml").exists()
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest syllabus/tests/test_export_cog.py::test_cli_writes_package -v`
Expected: FAIL, exit code 2 ("No such command 'export-cog'")

- [ ] **Step 3: Implement** (add this to `syllabus/cli/main.py`)

```python
@app.command("export-cog")
def export_cog_cmd(course_json: Path, slug: str, out_dir: Path) -> None:
    """Export a CourseSpec JSON as a Cogtraining course package (draft)."""
    from syllabus.export.cog import export_cog
    from syllabus.models.schemas import CourseSpec

    spec = CourseSpec.model_validate_json(course_json.read_text())
    target = out_dir / slug
    target.mkdir(parents=True, exist_ok=True)
    for name, text in export_cog(spec, slug).items():
        (target / name).write_text(text)
    typer.echo(f"wrote {target}")
```

Add `from pathlib import Path` to the imports if it isn't already there.

- [ ] **Step 4: Run the test file**

Run: `pytest syllabus/tests/test_export_cog.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add syllabus/cli/main.py syllabus/tests/test_export_cog.py
git commit -m "feat: add export-cog CLI command"
```

---

### Task 3: Catalog intake presets

**Files:**
- Create: `catalog/presets.json`
- Test: `syllabus/tests/test_catalog_presets.py`

**Interfaces:**
- Produces: `catalog/presets.json`, a list of `{"slug": str, "intake": IntakeData}`. These are the inputs to the existing `generate` command.

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

from syllabus.models.schemas import IntakeData

PRESETS = Path(__file__).resolve().parents[2] / "catalog" / "presets.json"


def test_presets_valid_and_unique():
    presets = json.loads(PRESETS.read_text())
    slugs = [p["slug"] for p in presets]
    assert len(slugs) == len(set(slugs)) >= 5
    for p in presets:
        IntakeData.model_validate(p["intake"])
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest syllabus/tests/test_catalog_presets.py -v`
Expected: FAIL with `FileNotFoundError`

- [ ] **Step 3: Create `catalog/presets.json`**

```json
[
  {"slug": "fertility-foundations", "intake": {"journey_stage": "thinking about starting", "confusion": "where do I even begin with fertility", "level": "beginner", "target_end_state": "Understand how fertility works and know the first practical steps to take."}},
  {"slug": "trying-to-conceive", "intake": {"journey_stage": "trying to conceive", "confusion": "timing, tracking and when to seek help", "level": "beginner", "target_end_state": "Track cycles confidently and know when to see a specialist."}},
  {"slug": "starting-ivf", "intake": {"journey_stage": "starting treatment", "diagnosis": "unexplained infertility", "confusion": "what happens during an IVF cycle", "level": "beginner", "target_end_state": "Walk into an IVF cycle knowing each step, medication and decision point."}},
  {"slug": "ttc-with-pcos", "intake": {"journey_stage": "trying to conceive", "diagnosis": "PCOS", "confusion": "how PCOS affects ovulation and treatment options", "level": "beginner", "target_end_state": "Understand PCOS-specific options and questions to ask a clinician."}},
  {"slug": "after-an-unsuccessful-cycle", "intake": {"journey_stage": "unsuccessful but hopeful", "confusion": "what to do after a failed cycle", "level": "intermediate", "target_end_state": "Review a failed cycle with your clinic and plan next steps."}}
]
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `pytest syllabus/tests/test_catalog_presets.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add catalog/presets.json syllabus/tests/test_catalog_presets.py
git commit -m "feat: add catalog intake presets by journey stage"
```

---

### Task 4: Create the `fertilityshare-learn` repo from cogtraining

**Files:** a new repo at `~/Documents/GitHub/fertilityshare-learn`

- [ ] **Step 1: Copy without history or build artifacts**

```bash
cd ~/Documents/GitHub && rsync -a --exclude node_modules --exclude .git --exclude '.next' --exclude '* 2.*' --exclude '* 2' --exclude '.env*' --exclude '.dev.vars' --exclude '*.pem' --exclude '*.key' cogtraining/ fertilityshare-learn/
# keep the example files the excludes above dropped
for f in .env.example .dev.vars.example; do [ -f cogtraining/$f ] && cp cogtraining/$f fertilityshare-learn/$f; done
cd fertilityshare-learn && git init && git add -A
# inspect staged files for secrets before the first commit
git diff --cached --name-only | grep -iE '\.env|\.dev\.vars|\.pem|\.key|secret|credential' # only *.example files may appear
git commit -m "chore: copy cogtraining engine as starting point"
```

Review the `git diff --cached --name-only` list by eye before committing; if anything secret-like is staged, `git rm --cached` it and add it to `.gitignore`.

- [ ] **Step 2: Remove dementia-specific content and docs**

```bash
git rm -r content/courses/* docs/1[0-3]-*.md docs/42-cms-migration-evidence.md Cognition-Network-Member-Deck*
git commit -m "chore: remove cogtraining course content and accreditation docs"
```

- [ ] **Step 3: Rebrand.** List every brand reference with `git grep -nI -e Cogtraining -e cogtraining.org -e CogTraining -e DEMENTIA-READY -e CDCP -e CCCS -- apps packages`. Replace the name with "FertilityShare Learn", the domain with `learn.fertilityshare.com`, and the colours with the FertilityShare teal from fertilityshare.com in the design tokens (`packages/ui`). Remove credential names.

- [ ] **Step 4: Verify the engine still builds.** Run `pnpm install && pnpm typecheck && pnpm lint && pnpm test && pnpm build`. Expected: all pass. Fix any test that asserts on Cogtraining copy or course ids, changing its expected value to the FertilityShare equivalent.

- [ ] **Step 5: Commit and push**

```bash
git add -A && git commit -m "feat: rebrand engine as FertilityShare Learn"
gh repo create abhishekshankar/fertilityshare-learn --private --source . --push
```

---

### Task 5: Import the pilot course end to end

**Interfaces:**
- Consumes: the `export-cog` output (Task 2) and the presets (Task 3)

- [ ] **Step 1: Generate and export the pilot** (in the `fertilityshare` repo)

```bash
python -m syllabus generate --help   # confirm flag names, then generate from the fertility-foundations preset into out/fertility-foundations.json
python -m syllabus export-cog out/fertility-foundations.json fertility-foundations ../fertilityshare-learn/content/courses
```

- [ ] **Step 2: Run content gates** (in `fertilityshare-learn`): `pnpm content:lint && pnpm accessibility:content && pnpm reading-level:check`. Fix the export in Task 1's code, not the generated files, if a gate rejects a field shape. Add a regression test for that shape in `test_export_cog.py`.

- [ ] **Step 3: Register the course** in `packages/course/src/` the same way `caf.ts` registered CAF. Copy `caf.ts` to `fertility-foundations.ts`, point it at the new directory, and copy `caf.test.ts` to match. Run `pnpm --filter course test`. Expected: PASS.

- [ ] **Step 4: Journey test.** Copy the CAF learner journey Playwright test and point it at `fertility-foundations`: enrol → complete all modules → pass the final assessment → certificate shown. Run `pnpm test:journeys`. Expected: PASS.

- [ ] **Step 5: Commit** in both repos (the presets and the out JSON in `fertilityshare`; the course content and registration in `fertilityshare-learn`).

---

### Task 6: Deploy to learn.fertilityshare.com

- [ ] **Step 1:** Create Neon and Cloudflare resources following `docs/25-infrastructure-and-cicd.md` in the learn repo, with new names (`fertilityshare-learn-*`). Do not reuse cogtraining ids.
- [ ] **Step 2:** Add the custom domain `learn.fertilityshare.com` to the Worker in Cloudflare (same account as the fertilityshare.com DNS).
- [ ] **Step 3:** Deploy using the repo's CI deploy job. Verify that `curl -s https://learn.fertilityshare.com/health` returns 200.
- [ ] **Step 4:** Keep the pilot unpublished until the clinical reviewer signs off. Then flip `status: published` and `draft_for_clinical_review: false` in its `course.yml` and redeploy.

---

### Task 7: Point fertilityshare.com at Learn; retire the Syllabus app

- [ ] **Step 1:** In WordPress (fertilityshare.com), set the "Learn" menu item URL to `https://learn.fertilityshare.com`. This is manual, in Appearance → Menus.
- [ ] **Step 2:** In this repo, remove the dead deploy path:

```bash
git rm .github/workflows/deploy.yml railway.json Procfile nixpacks.toml
git commit -m "chore: retire Railway/Vercel deploy; Syllabus is CLI-only"
```

- [ ] **Step 3:** Update the `README.md` intro to say that Syllabus generates and exports courses for FertilityShare Learn, with no hosted app. Commit.
- [ ] **Step 4:** Delete the Vercel project behind fertilityshare.vercel.app and any leftover Railway project. This is done manually by the owner.
