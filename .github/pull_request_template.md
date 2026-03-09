## Context

- **PRD:** [prd.md](../prd.md) (SYLLABUS-PRD-001 v2.0.0)
- **Scope:** V0 pipeline + CLI | V1 web/SSE/auth | V2 monetization/sharing

## Description

<!-- What does this PR do? Link to feature (F-XXX), user story (US-XXX), or task (T-XXX) if applicable. -->

## Type of change

- [ ] Bug fix
- [ ] New feature (PRD-aligned)
- [ ] Refactor / tech debt
- [ ] Docs or config only

## Checklist

- [ ] CI passing: lint (Ruff), test (pytest), build; SonarCloud, CodeQL, Gitleaks, Trivy (see [docs/CI.md](../docs/CI.md))
- [ ] Tests added/updated and passing (`pytest syllabus/tests -v`)
- [ ] No new linter errors (`ruff check .` and `ruff format --check .`)
- [ ] No secrets or API keys in code or commits
- [ ] Pipeline/lesson changes: every lesson still has a `compliance_note` block (F-003); no prescriptive medical advice
- [ ] DB/schema changes: new migration added (no DB reset)

## Agent boundaries (PRD 7.1)

- **Always:** Run tests before committing; follow existing patterns; match I/O contracts (Section 5.3).
- **Never:** Commit secrets; skip tests/lint; generate prescriptive medical advice; bypass the QA node.

## Notes for reviewers

<!-- Optional: areas to focus on, follow-up work, or known limitations -->
