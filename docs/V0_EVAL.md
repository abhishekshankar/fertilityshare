# V0 manual evaluation

## Running the 10-prompt eval

From the repo root, with `OPENAI_API_KEY` set (e.g. in `.env`):

```bash
python -m syllabus eval --out-dir out
```

To run eval and score on the 9-dimension rubric in one go:

```bash
python -m syllabus eval --out-dir out --rubric --report out/scorecard.json --markdown out/scorecard.md
```

Or with a custom prompts JSON file:

```bash
python -m syllabus eval --prompts syllabus/tests/fixtures/v0_prompts.json --out-dir out
```

This runs the pipeline for each of the 10 V0 test prompts (PRD Section 8.3) and writes one CourseSpec JSON per prompt to `out/course_01.json` … `out/course_10.json`.

## Success criteria (V0)

- **CLI**: `generate` and `eval` complete without error when the API key is set.
- **Schema**: Every output file is valid CourseSpec JSON (Pydantic-valid).
- **Compliance**: Every lesson in every course has at least one `compliance_note` block with “what to ask your RE” style content; no prescriptive language.
- **Rubric**: 8/10 courses pass the 5-dimension manual rubric (medical accuracy, structure, tone, compliance, completeness).

## 5-dimension rubric (PRD 8.2)

| Dimension | Pass | Fail |
|-----------|------|------|
| Medical accuracy | Facts correct; no prescriptive advice | Any factual error or prescriptive statement |
| Structural coherence | Lessons build logically; no gaps | Random ordering or missing prerequisites |
| Tone | Empathetic, warm, accessible | Clinical, cold, or condescending |
| Compliance | Every lesson has `compliance_note` block | Any lesson missing it |
| Completeness | Quizzes/flashcards present where specified | Missing in any lesson |

## Automated checks (optional)

After running `eval`, you can validate structure and compliance programmatically:

- Load each `out/course_*.json` and validate with `CourseSpec.model_validate(data)`.
- For each lesson, assert at least one block has `type == "compliance_note"` and content suggests asking a doctor/RE.

Unit and integration tests (see `syllabus/tests/`) already cover intent sanitization, QA rules, and a full pipeline run with mocked LLMs.

---

## Layer 1 eval (PRD Addendum E.3 — 9-dimension rubric)

**Layer 1 prompt upgrades are implemented.** To validate with the 9-dimension rubric:

1. **Run 10 prompts and score (treatment):**
   ```bash
   python -m syllabus eval --out-dir out --rubric --report out/scorecard.json --markdown out/scorecard.md
   ```
2. **Or score an existing directory:**
   ```bash
   python -m syllabus eval-rubric --out-dir out --report out/scorecard.json --markdown out/scorecard.md
   ```

**Success (E.3):** 8/10 courses pass all 9 dimensions (no automated fail); treatment ≥ baseline on original 5 dimensions and ≥ 7/10 on dimensions 6–9. **Rollback** if treatment scores &lt; baseline on any original dimension.

### 9-dimension rubric (E.1)

| # | Dimension | Pass | Fail | Automated |
|---|-----------|------|------|-----------|
| 1 | Medical accuracy | Facts correct; no prescriptive advice | Factual error or prescriptive statement | Yes |
| 2 | Structural coherence | Lessons build logically; no gaps | Random order or missing prerequisites | Human review |
| 3 | Tone | Empathetic, warm, accessible | Clinical, cold, condescending | Human review |
| 4 | Compliance | Every lesson has `compliance_note` | Any lesson missing it | Yes |
| 5 | Completeness | Quizzes/flashcards where warranted | Missing in appropriate lessons | Human review |
| 6 | Objective coherence | target_end_state present; every lesson serves arc | Missing target_end_state or lesson not serving arc | Heuristic (presence of target_end_state) |
| 7 | Scaffolding quality | Backward arc; ≤4 modules; one-concept-per-lesson | Arc from topic start; >1 concept/lesson; >4 modules | Heuristic |
| 8 | Knowledge topology fit | Method matches content type | Same block mix regardless; quiz after emotional | Human review |
| 9 | Emotional calibration | Reflection (not quiz) after emotional content | Quiz after high-sensitivity content | Heuristic (when schema has emotional_sensitivity_level) |
