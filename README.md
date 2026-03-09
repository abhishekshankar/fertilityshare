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
- **Index RAG**
  ```bash
  python -m syllabus index-rag /path/to/docs
  ```

## Tests

```bash
pytest syllabus/tests -v
```

## Manual eval

See [docs/V0_EVAL.md](docs/V0_EVAL.md) for the 10 prompts, success criteria, and 5-dimension rubric.

## Layout

- `syllabus/api/` — FastAPI app (auth, generate, course, progress, feedback)
- `syllabus/db/` — SQLAlchemy models, async session; `alembic/` migrations
- `syllabus/rag/` — Chroma store, indexing, `query_facts` for research
- `syllabus/pipeline/` — LangGraph nodes (intent, outline, research, content, qa) and graph
- `syllabus/models/` — Pydantic schemas (Intake, CourseSpec, Module, Lesson, ContentBlock)
- `syllabus/cli/` — Typer CLI (generate, eval, index-rag)
- `web/` — Next.js app (intake, stream, course, dashboard, login, waitlist)
- `syllabus/tests/` — Unit and integration tests

PRD: [prd.md](prd.md).
