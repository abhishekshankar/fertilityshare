# GitHub PR reviews (fetched)

All pull request reviews and inline comments from **abhishekshankar/fertilityshare**, as of the latest fetch.

---

## PR #1 — fix: Get CI green (ruff lint + format)

**Reviews:** Sourcery (positive), Cursor Bugbot ×2 (1 potential issue)

### Inline comments

| File | Author | Summary |
|------|--------|--------|
| `syllabus/pipeline/research.py` ~L60 | cursor[bot] | **Medium:** Lint fix removed `as e` from `except Exception`; real issue is returning `"error": None` on exception. Other nodes use `"error": str(e)`. Fix: propagate error (e.g. `"error": str(e)`) so failures in `run_research` are visible. |
| `syllabus/api/rate_limit.py` ~L8 | cursor[bot] | **Low:** `from slowapi.util import get_remote_address` is shadowed by a local `get_remote_address`; imported name never used. Remove the unused import. |

---

## PR #2 — fix: CI lint, format, SonarCloud, Trivy, and dependency-scan fixes

**Reviews:** Sourcery (multiple comments)

### Inline comments (excerpt)

| File | Author | Summary |
|------|--------|--------|
| `.github/workflows/quality.yml` | sourcery-ai[bot] | **Security:** Pin Sonar quality gate action to a version (e.g. `@v1.1.0`) instead of `@master`. |
| `syllabus/rag/pubmed.py` | sourcery-ai[bot] | **Suggestion:** One failing PubMed request aborts whole run. Wrap per-query fetch in try/except `httpx.HTTPError`, log and continue with other queries. |
| (Additional comments in same PR on pubmed.py and other files — see [PR #2 comments](https://github.com/abhishekshankar/fertilityshare/pull/2).) |

---

## PR #3 — feat: promote v1-mvp staging to main

**Reviews:** Sourcery (1 issue + high-level feedback)

### Overall feedback

- `_key_by_forwarded` in `test_rate_limit.py` duplicates rate-limit key logic; consider using the real implementation from `syllabus.api.rate_limit`.
- Plan follow-up to remove `feat/v1-mvp` from CI/quality/CodeQL once MVP is merged.

### Inline comments

| File | Author | Summary |
|------|--------|--------|
| `.github/workflows/ci.yml` ~L7 | sourcery-ai[bot] | **Question:** `workflow_dispatch` is not branch-scoped. Consider documenting that manual runs are for staging/main/feat/v1-mvp, or add branch input + `if:` guards. |

---

## PR #4 — ci: SonarCloud on push to default branch + Option A fixes

**Reviews:** Sourcery (1 issue + high-level feedback)

### Overall feedback

- Prefer `# noqa: BLE001` on specific lines for broad `Exception` handling instead of per-file ignores in pyproject.toml.
- With SonarCloud no longer `continue-on-error`, consider retries or handling of intermittent failures so they don’t block merges.

### Inline comments

| File | Author | Summary |
|------|--------|--------|
| `syllabus/tests/test_rate_limit.py` ~L49–52 | sourcery-ai[bot] | **Suggestion:** Assert `Retry-After` value (e.g. positive integer or valid HTTP date), not just presence. Example: get header, assert not None, `assert retry_after.isdigit()` and `int(retry_after) > 0`. |

---

## PR #5 — fix(sonar): address SonarCloud bugs and code smells

**Reviews:** Sourcery — “look great”; no inline comments.

---

## PR #6 — feat: promote feat/v1-mvp to main (staging → production)

**Reviews:** Sourcery (high-level feedback only)

### Overall feedback

- Bearer token parsing is duplicated in `get_current_user` and `get_current_user_for_stream`; extract e.g. `parse_bearer_token(authorization: str | None) -> str | None` with shared `BEARER_PREFIX`.
- In `rag.index`, exception handling was narrowed to `OSError`; if you want to skip decoding issues, consider also catching `UnicodeDecodeError` or add a short comment that non-OS errors are intentionally surfaced.

---

## PR #7 — OAuth callback: redirect to home when token present, show errors on login

**Reviews:** Sourcery — 3 issues (debug instrumentation)

### Overall feedback

- `_debug_log` in `auth.py`: hard-coded absolute path and inline `json` import; remove or use logging + configurable path.
- Frontend debug `fetch` to `http://127.0.0.1:7783/ingest/...` with fixed session/hypothesis IDs: gate behind env flag or remove to avoid leaking URLs/IDs in non-dev.

### Inline comments

1. **auth.py — `_debug_log`:** Avoid hard-coded user-specific path and dynamic imports; use logging and configurable path; move imports to module top.
2. **auth.py — `_debug_log` calls:** Security: audit/remove or gate behind env; ensure no tokens/user IDs are logged.
3. **Frontend callback (e.g. callback page):** Remove or make configurable the localhost debug endpoint and session IDs; ensure disabled in production.

---

## PR #8 — feat: promote feat/v1-mvp to main (staging → production)

**Reviews:** Sourcery — 1 issue (same theme as PR #7)

### Overall feedback

- Remove or replace `_debug_log` (hard-coded path) with logging/configurable path before promoting to main.
- Remove, feature-flag, or route client-side debug `fetch` to a proper telemetry endpoint; avoid silent exception swallowing in debug path.

### Inline comments

| Location | Summary |
|----------|--------|
| Client callback (fetch to 127.0.0.1:7783) | **Bug risk:** Hard-coded localhost and session IDs in client bundle; runs in production. Gate behind dev-only flag or remove from production builds. |

---

## PR #9 — chore: sync staging with main (7 commits)

**Reviews:** Sourcery — 3 issues

### Overall feedback

- `_debug_log` still uses hard-coded user path; guard file writes with env flag and/or configurable log directory.
- Multiple `id === "undefined"` guards suggest fixing ID generation/serialization at the API/link source instead of scattering guards.

### Inline comments

1. **Password truncation for bcrypt:** Truncation with `decode(errors="replace")` can change bytes and break compatibility for some >72-byte passwords. Prefer truncating on character boundaries, preserving first 72 bytes, or using a 1:1 mapping (e.g. latin-1) for truncation only.
2. **jobId / "undefined":** Prefer validating generically (null/empty/non-numeric) rather than checking for the string `"undefined"`; better to fix where `job_id` is produced.
3. **Course list `key` and `href`:** When `c.id` is missing, `key={c.id}` can be undefined (React warnings). Filter items without `id` or use a safe fallback; avoid `href="#"` for items without id — use non-link or disabled styling instead.

---

## Summary table

| PR | Title | Reviewers | Actionable items |
|----|--------|-----------|------------------|
| 1 | fix: Get CI green | Sourcery, Cursor | research.py error propagation; rate_limit.py remove shadowed import |
| 2 | CI + SonarCloud/Trivy fixes | Sourcery | Pin quality gate action; PubMed resilience (try/except per query) |
| 3 | promote v1-mvp to main | Sourcery | workflow_dispatch docs/guards; test_rate_limit use real key logic |
| 4 | SonarCloud on push + Option A | Sourcery | Assert Retry-After value in test_rate_limit |
| 5 | SonarCloud bugs and code smells | Sourcery | None |
| 6 | promote feat/v1-mvp to main | Sourcery | Extract parse_bearer_token; rag index UnicodeDecodeError/comment |
| 7 | OAuth callback redirect/errors | Sourcery | Remove/gate _debug_log and frontend debug fetch |
| 8 | promote feat/v1-mvp to main | Sourcery | Same debug fetch / _debug_log as PR #7 |
| 9 | sync staging with main | Sourcery | bcrypt truncation; jobId validation; course list key/href |

---

*Generated from GitHub API: `GET /repos/abhishekshankar/fertilityshare/pulls` and `/pulls/{n}/reviews`, `/pulls/{n}/comments`.*
