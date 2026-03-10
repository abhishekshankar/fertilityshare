"""Fetch PubMed abstracts and index them into the RAG vector store (PRD T-012)."""

import time
from typing import Any

import httpx

from syllabus.rag.index import index_documents

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# Rate limit: 3 requests/sec without API key
REQUEST_DELAY = 0.34

# V1 target ~500 docs: DEFAULT_MAX_PER_QUERY × len(DEFAULT_QUERIES) ≈ 500 chunks
DEFAULT_MAX_PER_QUERY = 50

# Default fertility-related queries for V1 (ASRM/PubMed scope)
DEFAULT_QUERIES = [
    "IVF in vitro fertilization",
    "PCOS polycystic ovary fertility",
    "AMH ovarian reserve",
    "IUI intrauterine insemination",
    "egg freezing oocyte cryopreservation",
    "male factor infertility",
    "embryo transfer",
    "ovarian stimulation protocol",
    "recurrent pregnancy loss",
    "endometriosis fertility",
]


def _esearch(query: str, retmax: int, client: httpx.Client) -> list[str]:
    """Return list of PMIDs for the query."""
    r = client.get(
        f"{BASE_URL}/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retmode": "json",
        },
        timeout=30.0,
    )
    r.raise_for_status()
    data: dict[str, Any] = r.json()
    id_list = data.get("esearchresult", {}).get("idlist") or []
    return id_list


def _efetch_abstracts(pmids: list[str], client: httpx.Client) -> list[tuple[str, str]]:
    """Fetch abstracts for PMIDs. Returns list of (source_id, text)."""
    if not pmids:
        return []
    time.sleep(REQUEST_DELAY)
    r = client.get(
        f"{BASE_URL}/efetch.fcgi",
        params={
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "abstract",
            "retmode": "text",
        },
        timeout=60.0,
    )
    r.raise_for_status()
    text = r.text
    # efetch retmode=text returns blocks starting with "PMID: 12345" or similar
    out: list[tuple[str, str]] = []
    blocks = text.split("PMID:")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        first = lines[0].strip()
        # First line is the number (and possibly more); rest is title/abstract
        pmid = first.split()[0] if first else ""
        if not pmid or not pmid.isdigit():
            continue
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        if not body:
            body = first
        out.append((f"PubMed:{pmid}", body))
    return out


def fetch_abstracts_for_query(
    query: str,
    max_results: int,
    client: httpx.Client | None = None,
) -> list[tuple[str, str]]:
    """
    Fetch up to max_results abstracts for a single query.
    Returns list of (source_id, text) e.g. ("PubMed:12345", "Abstract...").
    """
    own_client = client is None
    if client is None:
        client = httpx.Client()
    try:
        pmids = _esearch(query, retmax=max_results, client=client)
        time.sleep(REQUEST_DELAY)
        return _efetch_abstracts(pmids, client)
    finally:
        if own_client:
            client.close()


def index_pubmed(
    queries: list[str] | None = None,
    max_per_query: int = DEFAULT_MAX_PER_QUERY,
) -> int:
    """
    Fetch PubMed abstracts for the given queries (or default fertility queries)
    and index them into the RAG store. Returns number of chunks indexed.
    """
    queries = queries or DEFAULT_QUERIES
    documents: list[tuple[str, str]] = []
    with httpx.Client() as client:
        for q in queries:
            docs = fetch_abstracts_for_query(q, max_per_query, client=client)
            documents.extend(docs)
    if not documents:
        return 0
    return index_documents(documents)
