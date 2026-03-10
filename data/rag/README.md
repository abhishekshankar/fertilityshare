# RAG source content (PRD T-012)

This folder holds **ASRM and other fertility reference content** for the RAG vector store. The pipeline’s ResearchNode uses this store to ground lessons in evidence (PRD Section 5.2).

## Indexing

1. **PubMed abstracts** (no files here):
   ```bash
   python -m syllabus index-pubmed
   ```
   Optional: `-n 50` (max per query), `-q "IVF" -q "PCOS"` (custom queries).

2. **ASRM / local documents**:
   - Add `.txt` or `.md` files under `data/rag/` (or any directory).
   - Run:
   ```bash
   python -m syllabus index-rag data/rag
   ```
   All `.txt`/`.md` under the path are chunked, embedded, and added to the same Chroma collection.

## V1 scale

- PRD target: **500** documents (ASRM + PubMed) for V1.
- Store path: `RAG_INDEX_PATH` (default `.chroma_rag`).

## ASRM content

ASRM patient fact sheets and guidelines are not bundled here for licensing. Add your own exported or licensed text as `.txt`/`.md` and run `index-rag` on that directory.
