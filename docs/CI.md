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

## Branch protection

Required status checks on `staging` and `main`: `lint-test-build`, `sonarcloud`, `secrets-scan`, `dependency-scan`, `analyze`, plus at least one approving review. See [codereviewworkflow.md](../codereviewworkflow.md#branch-protection-checklist).
