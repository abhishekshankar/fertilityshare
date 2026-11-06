# FertilityShare Learn — design

Date: 2026-11-06 · Status: draft for review

## Goal

Give FertilityShare a working "Learn" product: a course catalog with progress, knowledge checks, an AI tutor with citations, and certificates. Reuse the cogtraining.org learning engine instead of running the Syllabus web app and its Railway backend.

## Decisions (agreed)

1. **Platform:** the Cogtraining engine.
2. **Reuse method:** copy the `cogtraining` repo into a new `fertilityshare-learn` repo, rebrand it, and deploy it separately. cogtraining.org is not touched.
3. **Course model:** a shared catalog. Every learner sees the same courses; personal help comes from the AI tutor, grounded in the course material. No per-learner generated courses.

## Defaults (change during review if wrong)

- **Domain:** `learn.fertilityshare.com` (Cloudflare DNS). The "Learn" menu on fertilityshare.com links there, replacing the broken `/courses/` page.
- **Catalog:** follows the community's journey stages: Thinking about starting → Trying to conceive → Starting treatment (IVF/IUI) → Unsuccessful but hopeful → Pregnancy after fertility treatment.
- **Pilot:** one free foundations course, shipped end to end, before more courses are added.
- **Pricing:** the foundations course is free. Deeper courses map to the existing plans: Ready $15/mo and Premium $25/mo.
- **Email and community:** these stay where they are (Discourse, and Brevo for email). newsletter.stream is out of scope.

## Architecture

```
Syllabus pipeline (this repo, CLI only)
  intake preset ─▶ LangGraph pipeline ─▶ CourseSpec JSON
                                            │
                          syllabus export-cog (new)
                                            ▼
                 course package: course.yml + mNN-*.md + final-assessment.md
                                            │  status: draft, draft_for_clinical_review: true
                                            ▼
fertilityshare-learn (copy of cogtraining)
  content lint + reading level + a11y checks ─▶ clinical review ─▶ CMS import ─▶ publish
  Next.js on Cloudflare Workers · Neon · CMS · tutor (RAG + citations) · exams · certificates
```

### Units

1. **`fertilityshare-learn` repo.** Copied from `cogtraining`. Swap the brand (name, colours, copy, domain, legal and safety footer) and remove the dementia-specific courses, credentials and accreditation docs. Keep the engine: course player, quizzes/exams, tutor, progress, certificates, auth, payments, CMS import.
2. **`syllabus export-cog` CLI command** (in this repo). Converts a `CourseSpec` into a cogtraining course package. It is a pure function with no network access. Mapping:
   - CourseSpec → `course.yml` (id, title, slug, summary, tier, `status: draft`, `draft_for_clinical_review: true`, fertility safety footer)
   - Syllabus module → `groups` entry (a Part)
   - Syllabus lesson → one `mNN-<slug>.md` module file. Its blocks and key takeaways become the body, and citations go into the frontmatter `citations`.
   - Lesson quiz → that module's quick-check questions
   - `final-assessment.md` → built from the lessons' quiz questions, pass mark 4 of 6
   - Flashcards → dropped (the engine has no equivalent; YAGNI)
3. **Intake presets.** One preset per catalog course (journey stage, diagnosis, level, target end state), stored in the repo, so courses can be regenerated.
4. **Clinical review gate.** Nothing is published until a named fertility clinician signs off. This uses the engine's existing `draft_for_clinical_review` flag.

## Retired

- The Syllabus web app (Vercel) and FastAPI backend (Railway), along with their auth, database and SSE streaming. The pipeline and the CLI stay.
- The `deploy.yml` Railway and Vercel jobs, once the learn site is live.

## Error handling

- `export-cog` refuses a CourseSpec that has no lessons, empty blocks, or a lesson without a title, and exits non-zero with the course and lesson id.
- The engine's existing content lint must pass before any import; a lint failure blocks the import.

## Testing

- `export-cog`: one pytest that converts `out/course_01.json` and asserts the file set, `course.yml` fields, frontmatter, and quick-check count.
- Learn repo: the engine's existing suites (typecheck, lint, journeys, a11y), run after the rebrand. Plus one journey test: enrol in the pilot course, finish it, pass the final assessment, receive the certificate.

## Open business decisions (not design blockers)

- Who the clinical reviewer is (the launch blocker).
- Which pilot course title to start with.
- Whether to keep certificates as a "completion badge" (recommended) and not a professional credential.
