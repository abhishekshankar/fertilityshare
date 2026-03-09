"""Vector store (Chroma) for RAG; query returns key facts + optional citations."""

import os
from typing import Any

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

COLLECTION_NAME = "syllabus_rag"
RAG_INDEX_PATH = os.environ.get("RAG_INDEX_PATH", ".chroma_rag")
TOP_K = 5


def _get_client():
    return chromadb.PersistentClient(path=RAG_INDEX_PATH, settings=Settings(anonymized_telemetry=False))


def _get_embedding_function():
    return embedding_functions.OpenAIEmbeddingFunction(
        api_key_env_var="OPENAI_API_KEY",
        model_name=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    )


def get_store():
    """Return Chroma collection for syllabus RAG (creates if missing)."""
    client = _get_client()
    try:
        return client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=_get_embedding_function(),
        )
    except Exception:
        return client.create_collection(
            name=COLLECTION_NAME,
            embedding_function=_get_embedding_function(),
        )


def query_facts(
    query: str,
    n_results: int = TOP_K,
    intake_context: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Query the vector store; return (concatenated facts string, list of {source, snippet} for citations).
    If store is empty or query fails, return stub text and empty citations.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        return (
            "Key concepts and evidence-based points for this topic (RAG not configured).",
            [],
        )
    try:
        coll = get_store()
        if coll.count() == 0:
            return (
                "Key concepts and evidence-based points for this topic (index empty; add documents first).",
                [],
            )
        combined = query
        if intake_context:
            combined = f"{query}\nContext: {intake_context}"
        results = coll.query(
            query_texts=[combined],
            n_results=n_results,
            include=["documents", "metadatas"],
        )
        documents = results.get("documents") or [[]]
        metadatas = results.get("metadatas") or [[]]
        docs = documents[0] if documents else []
        metas = metadatas[0] if metadatas else []
        facts_parts = []
        citations = []
        for i, doc in enumerate(docs):
            if doc:
                facts_parts.append(doc.strip())
                meta = metas[i] if i < len(metas) else {}
                citations.append({
                    "source": meta.get("source", "Source"),
                    "snippet": doc.strip()[:300],
                })
        facts_str = "\n\n".join(facts_parts) if facts_parts else (
            "Key concepts and evidence-based points for this topic (no close match in index)."
        )
        return facts_str, citations
    except Exception:
        return (
            "Key concepts and evidence-based points for this topic (RAG query failed; using fallback).",
            [],
        )
