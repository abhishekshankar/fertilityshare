# Finish real RAG (V1 research grounding)

The pipeline **already uses real RAG** when the vector store has data. ResearchNode calls `query_facts()`; if the Chroma collection is empty or the query fails, it falls back to stub text and no citations. To get real evidence and citations in lessons:

---

## 1. Prerequisites

- **OPENAI_API_KEY** set (used for embeddings and the pipeline). Without it, indexing and retrieval both no-op or fall back.
- Optional: **RAG_INDEX_PATH** (default: `.chroma_rag`) — directory where Chroma persists the index. Set to a path that persists across deploys if you run in production.

---

## 2. Populate the index (pick one or both)

### Option A: PubMed (fertility abstracts)

No local files. Fetches abstracts from NCBI and indexes them.

```bash
python -m syllabus index-pubmed
```

- Uses 10 default fertility queries (IVF, PCOS, AMH, IUI, egg freezing, etc.), ~50 abstracts per query → ~500 chunks for V1.
- Optional: `-n 30` (fewer per query), or `-q "your query" -q "another"` for custom queries.

### Option B: Local / ASRM documents

Add `.txt` or `.md` files (e.g. under `data/rag/`), then:

```bash
python -m syllabus index-rag data/rag
```

Use any directory path; all `.txt`/`.md` under it are chunked and added to the same collection.

### Option C: Both

Run both commands. They write into the **same** Chroma collection (`syllabus_rag`), so lessons can be grounded in both PubMed and your own docs.

---

## 3. Verify

- Run a course generation (web intake or CLI). If the index has content, ResearchNode will return real snippets and citations; the first content block of a lesson can show "Sources: PubMed:12345 — ...".
- Or check collection size (e.g. in Python): `get_store().count()` (see `syllabus/rag/store.py`).

---

## Summary

| Step | Action |
|------|--------|
| 1 | Set `OPENAI_API_KEY` (and optionally `RAG_INDEX_PATH`) |
| 2 | Run `python -m syllabus index-pubmed` and/or `python -m syllabus index-rag <dir>` |
| 3 | Generate a course; lessons should include citations when RAG finds matches |

No code changes are required; the pipeline and store are already wired. See [data/rag/README.md](../data/rag/README.md) for ASRM content and V1 scale notes.
