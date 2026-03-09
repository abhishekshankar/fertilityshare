

## The Full Tool Stack

| Layer | Tool | Free? | What it catches |
|---|---|---|---|
| 1. Style/lint | ESLint + Prettier | Always free [ai-coding-flow](https://ai-coding-flow.com/blog/best-free-ai-code-review-tools-2026/) | Syntax, formatting, style rules |
| 2. Tests + build | GitHub Actions (built-in CI) | Free for public [docs.github](https://docs.github.com/en/billing/concepts/product-billing/github-code-quality) | Runtime correctness, broken builds |
| 3. Code quality | SonarCloud | Free for OSS [dev](https://dev.to/jei/part-2-automating-code-quality-scanning-using-sonar-cloud-and-github-actions-8g7) | Bugs, code smells, duplication, coverage |
| 4. Security | GitHub CodeQL | Free for public [ai-coding-flow](https://ai-coding-flow.com/blog/best-free-ai-code-review-tools-2026/) | Injection, path traversal, insecure patterns |
| 5. Secrets + deps | Gitleaks + Trivy | Always free [ai-coding-flow](https://ai-coding-flow.com/blog/best-free-ai-code-review-tools-2026/) | Leaked secrets, vulnerable dependencies |
| 6. AI review | CodeRabbit | Free for public [coderabbit](https://www.coderabbit.ai/open-source) | Logic issues, suggestions, PR summaries |
| 7. AI refactor | Sourcery | Free for public [github](https://github.com/sourcery-ai/action/blob/main/README.md) | Refactoring, readability, anti-patterns |
| 8. Human review | GitHub PR review | Built-in | Plan adherence, judgment calls |

## Workflow: Step-by-Step

```
Dev pushes to feature/xxx branch
        │
        ▼
[Layer 1] ESLint + Prettier (runs in < 30s)
        │  FAIL → PR blocked, no human review wasted
        ▼
[Layer 2] npm test + npm run build (CI)
        │  FAIL → PR blocked
        ▼
[Layer 3] SonarCloud Quality Gate
        │  FAIL if Quality Gate score < threshold → PR blocked
        ▼
[Layer 4] GitHub CodeQL security scan
        │  FAIL on critical/high CVEs → PR blocked
        ▼
[Layer 5] Gitleaks (secrets) + Trivy (deps/containers)
        │  FAIL on any secret or critical dep vuln → PR blocked
        ▼
[Layer 6] CodeRabbit AI review posts inline PR comments
[Layer 6] Sourcery AI posts refactor suggestions
        │  (informational — doesn't block but team must resolve)
        ▼
[Layer 7] Human review (you or another dev) ← now only judgment calls remain
        │  Approve
        ▼
Merge into staging
```

## GitHub Actions Files

Create these three files in `.github/workflows/`:

### `ci.yml` — Lint, Test, Build
```yaml
name: CI

on:
  pull_request:
    branches: [staging, main]

jobs:
  lint-test-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci
      - run: npm run lint         # ESLint
      - run: npm run format:check # Prettier
      - run: npm test -- --ci     # Jest/Vitest
      - run: npm run build
```

### `quality.yml` — SonarCloud + Security
```yaml
name: Code Quality & Security

on:
  pull_request:
    branches: [staging, main]

jobs:
  sonarcloud:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm test -- --ci --coverage
      - uses: sonarsource/sonarcloud-github-action@master
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}

  secrets-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  dependency-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aquasecurity/trivy-action@master
        with:
          scan-type: fs
          scan-ref: .
          severity: CRITICAL,HIGH
          exit-code: 1
```

### `codeql.yml` — Security Analysis
```yaml
name: CodeQL

on:
  pull_request:
    branches: [staging, main]

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: javascript
      - uses: github/codeql-action/autobuild@v3
      - uses: github/codeql-action/analyze@v3
```

CodeRabbit and Sourcery are installed via GitHub Marketplace (one-click install, no YAML needed) and auto-activate on every PR. [github](https://github.com/sourcery-ai/action/blob/main/README.md)

## Branch Protection Settings

Go to **Settings → Branches → Add Rule** on `staging` and `main`, and mark all of these as **required status checks**: [docs.github](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule)

- `lint-test-build` (from ci.yml)
- `sonarcloud` (from quality.yml)
- `secrets-scan`
- `dependency-scan`
- `analyze` (CodeQL)
- Require at least 1 approving review

This means a PR literally **cannot merge** unless every automated layer passes, and a human has reviewed it. [group107](https://group107.com/blog/code-review-best-practices/)

## What Each Layer Saves You

- Lint/Prettier: Removes 100% of "formatting debate" from human review. [ai-coding-flow](https://ai-coding-flow.com/blog/best-free-ai-code-review-tools-2026/)
- Tests + build: Catches broken code before anyone reads it. [devcom](https://devcom.com/tech-blog/ci-cd-code-review/)
- SonarCloud: Spots code smells and complexity before they become tech debt. [dev](https://dev.to/jei/part-2-automating-code-quality-scanning-using-sonar-cloud-and-github-actions-8g7)
- CodeQL: Catches SQL injection, XSS, and other security flaws that humans miss. [ai-coding-flow](https://ai-coding-flow.com/blog/best-free-ai-code-review-tools-2026/)
- Gitleaks: Stops API keys and tokens from ever landing in the repo. [ai-coding-flow](https://ai-coding-flow.com/blog/best-free-ai-code-review-tools-2026/)
- Trivy: Flags npm dependencies with known CVEs before they ship. [ai-coding-flow](https://ai-coding-flow.com/blog/best-free-ai-code-review-tools-2026/)
- CodeRabbit + Sourcery: By the time these run, only real logic and architecture questions remain for AI to comment on — less noise, higher signal. [coderabbit](https://www.coderabbit.ai/open-source)
- Human review: By this point, you only review *decisions*, not mechanics. [github](https://github.blog/developer-skills/github/how-to-review-code-effectively-a-github-staff-engineers-philosophy/)

---

## Implementation in this repo (Python)

This repo uses **Python** (not Node). The same layers are implemented as follows:

| Layer | In this repo |
|-------|----------------|
| 1 | **Ruff** (lint + format) — `ruff check .` and `ruff format --check .` |
| 2 | **pytest** + **python -m build** — see `.github/workflows/ci.yml` |
| 3 | **SonarCloud** — coverage from pytest-cov; requires `SONAR_TOKEN` in GitHub Secrets and `sonar-project.properties` (set `sonar.organization` and `sonar.projectKey` after creating the project on sonarcloud.io) |
| 4 | **CodeQL** with `languages: python` — `.github/workflows/codeql.yml` |
| 5 | **Gitleaks** + **Trivy** (fs scan) — `.github/workflows/quality.yml` |
| 6 | **CodeRabbit** and **Sourcery** — install from [GitHub Marketplace](https://github.com/marketplace); they comment on PRs and do not block merge. No YAML in repo. |
| 7 | **Human review** — require at least 1 approval via branch protection. |

### Branch protection checklist

In **Settings → Branches → Add rule** for `staging` and `main`, add these as **required status checks**:

- `lint-test-build` (from ci.yml)
- `sonarcloud` (from quality.yml)
- `secrets-scan`
- `dependency-scan`
- `analyze` (CodeQL)

Also enable **Require at least 1 approving review**. PRs cannot merge until all checks pass and a human has approved.

### CodeRabbit and Sourcery

Install from GitHub Marketplace (one-click). They run on every PR and post inline comments; they are informational and do not block merge. Resolve or acknowledge their suggestions as part of team workflow.