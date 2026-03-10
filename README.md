# Syllabus — AI fertility learning platform

V0: pipeline + schema + CLI. V1: FastAPI API, Postgres, auth (Google OAuth + email/password), RAG (Chroma), Next.js app (intake, stream, course, dashboard, feedback), invite-only.

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # set OPENAI_API_KEY, DATABASE_URL, JWT_SECRET, etc.
```

## V1: Run API + Web

1. **Database**
   ```bash
   export DATABASE_URL=postgresql://user:pass@localhost/syllabus   # or postgresql+asyncpg:// for app
   alembic upgrade head
   ```

2. **Backend**
   ```bash
   export OPENAI_API_KEY=sk-...
   export JWT_SECRET=your-secret
   # Optional: ALLOWED_EMAILS=you@example.com (comma-separated; invite-only)
   uvicorn syllabus.api.main:app --reload
   ```
   API: http://127.0.0.1:8000

3. **Frontend**
   ```bash
   cd web
   npm install
   npm run dev
   ```
   App: http://localhost:3000. Set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` if the API is elsewhere.

4. **Invite a user**  
   Add their email to `ALLOWED_EMAILS` in the backend env; they sign in (or register) and get access to intake/generate/dashboard.

5. **RAG (optional)**  
   Index docs so research uses real facts and citations:
   ```bash
   python -m syllabus index-rag /path/to/txt-or-md-files
   ```
   Without indexing, the pipeline uses a stub for research.

## CLI (V0 + V1)

- **Single course from prompt or JSON**
  ```bash
  python -m syllabus generate --prompt "I was just diagnosed with PCOS..."
  python -m syllabus generate --intake intake.json --out out/course.json
  ```
- **Run 10 V0 test prompts (eval)**
  ```bash
  python -m syllabus eval --out-dir out
  ```
- **Index RAG** (local .txt/.md)
  ```bash
  python -m syllabus index-rag /path/to/docs
  ```
- **Index PubMed** (fertility abstracts into RAG, PRD T-012)
  ```bash
  python -m syllabus index-pubmed
  ```
  Optional: `-n 50` (max per query), `-q "IVF" -q "PCOS"` (custom queries).

## RAG indexing

The pipeline’s ResearchNode grounds each lesson in evidence from a vector store (PRD T-012/T-013). Without indexing, it uses a stub.

| Source | Command | Default scope |
| :----- | :------ | :------------ |
| **PubMed** | `python -m syllabus index-pubmed` | 10 fertility queries (IVF, PCOS, AMH, IUI, egg freezing, male factor, embryo transfer, stimulation, pregnancy loss, endometriosis); 50 abstracts per query (~500 chunks). |
| **Local / ASRM** | `python -m syllabus index-rag <dir>` | All `.txt`/`.md` under the directory. |

- **V1 target:** 500 documents (ASRM + PubMed). Store path: `RAG_INDEX_PATH` (default `.chroma_rag`).
- **Details:** [data/rag/README.md](data/rag/README.md) — custom PubMed queries, adding ASRM content, and re-indexing.

## Tests

```bash
pytest syllabus/tests -v
```

**E2E (Playwright):** From `web/`, run `npm run test:e2e`. Requires the backend running and a test user in `ALLOWED_EMAILS`; set `E2E_TEST_EMAIL` and `E2E_TEST_PASSWORD` to run the intake → course flow spec.

## Manual eval

See [docs/V0_EVAL.md](docs/V0_EVAL.md) for the 10 prompts, success criteria, and 5-dimension rubric.

## Layout

- `syllabus/api/` — FastAPI app (auth, generate, course, progress, feedback)
- `syllabus/db/` — SQLAlchemy models, async session; `alembic/` migrations
- `syllabus/rag/` — Chroma store, indexing, `query_facts` for research
- `syllabus/pipeline/` — LangGraph nodes (intent, outline, research, content, qa) and graph
- `syllabus/models/` — Pydantic schemas (Intake, CourseSpec, Module, Lesson, ContentBlock)
- `syllabus/cli/` — Typer CLI (generate, eval, index-rag, index-pubmed)
- `web/` — Next.js app (intake, stream, course, dashboard, login, waitlist)
- `syllabus/tests/` — Unit and integration tests

## Production (Railway + Vercel)

Set production env vars in Railway and Vercel, and add the production callback URL in Google OAuth. See **[docs/PRODUCTION-ENV.md](docs/PRODUCTION-ENV.md)** for the full list and Google Cloud steps.

PRD: [prd.md](prd.md).
