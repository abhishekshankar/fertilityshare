"""Index documents into the RAG vector store (chunk, embed, add)."""

import os
import uuid
from pathlib import Path

from syllabus.rag.store import get_store


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c]


def index_documents(documents: list[tuple[str, str]]) -> int:
    """
    Index (source_id, text) pairs into the store. Each document is chunked and embedded.
    Returns number of chunks added.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        return 0
    store = get_store()
    all_ids = []
    all_docs = []
    all_metas = []
    for source_id, text in documents:
        chunks = _chunk_text(text)
        for i, chunk in enumerate(chunks):
            all_ids.append(f"{source_id}_{i}_{uuid.uuid4().hex[:8]}")
            all_docs.append(chunk)
            all_metas.append({"source": source_id})
    if all_ids:
        store.add(ids=all_ids, documents=all_docs, metadatas=all_metas)
    return len(all_ids)


def index_directory(path: str, extensions: tuple[str, ...] = (".txt", ".md")) -> int:
    """Load .txt and .md files from a directory and index them. Returns number of chunks added."""
    root = Path(path)
    if not root.is_dir():
        return 0
    documents = []
    for ext in extensions:
        for f in root.rglob(f"*{ext}"):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                source_id = str(f.relative_to(root))
                documents.append((source_id, text))
            except OSError:
                continue
    return index_documents(documents)


def index_file(file_path: str, source_id: str | None = None) -> int:
    """Index a single file. source_id defaults to filename."""
    path = Path(file_path)
    if not path.is_file():
        return 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        sid = source_id or path.name
        return index_documents([(sid, text)])
    except OSError:
        return 0
