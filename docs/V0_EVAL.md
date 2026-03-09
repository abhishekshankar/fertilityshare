# V0 manual evaluation

## Running the 10-prompt eval

From the repo root, with `OPENAI_API_KEY` set (e.g. in `.env`):

```bash
python -m syllabus eval --out-dir out
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
