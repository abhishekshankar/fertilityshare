# CI and code review

This repo runs the [code review workflow](../codereviewworkflow.md) (lint, test, SonarCloud, CodeQL, Gitleaks, Trivy) on every PR to `staging` and `main`.

## Run locally before pushing

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest syllabus/tests -v
python -m build
```

## Workflows

| Workflow | Job | What it does |
|----------|-----|----------------|
| **CI** (`ci.yml`) | `lint-test-build` | Ruff lint + format check, pytest, build |
| **Code Quality & Security** (`quality.yml`) | `sonarcloud` | Tests with coverage, uploads to SonarCloud |
| | `secrets-scan` | Gitleaks — detects committed secrets |
| | `dependency-scan` | Trivy — CRITICAL/HIGH vulns in repo |
| **CodeQL** (`codeql.yml`) | `analyze` | Static security analysis (Python) |

## SonarCloud

- Add **SONAR_TOKEN** in **Settings → Secrets and variables → Actions** (never commit the token).
- Create a project at [sonarcloud.io](https://sonarcloud.io) and set `sonar.organization` and `sonar.projectKey` in `sonar-project.properties` (or in SonarCloud UI).
- Analysis runs on **pull requests** (PR decoration) and on **push to `main`** (so the default branch is analyzed and the dashboard shows results). To analyze `main` once without merging: **Actions → Code Quality & Security → Run workflow**, then choose branch **main** and run.

### If the Quality Gate blocks the PR

The gate is evaluated on **new code** (e.g. the PR diff). To unblock:

1. **Fix the issues** — Open the PR report on SonarCloud (link in the failed check). Fix reported bugs, vulnerabilities, code smells, or add coverage for new code.
2. **Or use a different gate** — In SonarCloud: **Project Settings → Quality Gate**. Choose **None** (no gate) or create a **custom gate** with relaxed conditions (e.g. lower or no “Coverage on New Code” requirement). The default “Sonar way” gate is strict; many projects use a custom gate.

## Branch protection

Required status checks on `staging` and `main`: `lint-test-build`, `sonarcloud`, `secrets-scan`, `dependency-scan`, `analyze`, plus at least one approving review. See [codereviewworkflow.md](../codereviewworkflow.md#branch-protection-checklist).
