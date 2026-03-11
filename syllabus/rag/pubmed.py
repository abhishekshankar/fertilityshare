"""Fetch PubMed abstracts and index them into the RAG vector store (PRD T-012)."""

import logging
import time
from typing import Any

import httpx

from syllabus.rag.index import index_documents

logger = logging.getLogger(__name__)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# NCBI rate limit: 3 requests/sec without API key; use conservative delay to avoid 429
REQUEST_DELAY = 0.5
DELAY_BETWEEN_QUERIES = 1.0
MAX_RETRIES_429 = 5
RETRY_BACKOFF = 2.0

# V1 target ~500 docs: DEFAULT_MAX_PER_QUERY × len(DEFAULT_QUERIES); lower per-query to avoid 429
DEFAULT_MAX_PER_QUERY = 25

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


def _request_with_429_retry(
    client: httpx.Client,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Get with retries on 429 (rate limit)."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES_429):
        r = client.request(method, url, **kwargs)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        last_exc = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=r.request,
            response=r,
        )
        wait = RETRY_BACKOFF**attempt
        logger.warning(
            "PubMed 429 rate limit; waiting %.1fs before retry %d/%d",
            wait,
            attempt + 1,
            MAX_RETRIES_429,
        )
        time.sleep(wait)
    if last_exc:
        raise last_exc
    raise httpx.HTTPStatusError("429", request=None, response=None)  # type: ignore


def _esearch(query: str, retmax: int, client: httpx.Client) -> list[str]:
    """Return list of PMIDs for the query."""
    time.sleep(REQUEST_DELAY)
    r = _request_with_429_retry(
        client,
        "GET",
        f"{BASE_URL}/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retmode": "json",
        },
        timeout=30.0,
    )
    data: dict[str, Any] = r.json()
    id_list = data.get("esearchresult", {}).get("idlist") or []
    return id_list


def _efetch_abstracts(pmids: list[str], client: httpx.Client) -> list[tuple[str, str]]:
    """Fetch abstracts for PMIDs via XML for robust parsing. Returns list of (source_id, text)."""
    if not pmids:
        return []
    time.sleep(REQUEST_DELAY)
    r = _request_with_429_retry(
        client,
        "GET",
        f"{BASE_URL}/efetch.fcgi",
        params={
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "abstract",
            "retmode": "xml",
        },
        timeout=60.0,
    )
    import xml.etree.ElementTree as ET

    out: list[tuple[str, str]] = []
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        logger.warning("Failed to parse PubMed XML response; falling back to text splitting")
        return _efetch_abstracts_text_fallback(r.text)
    for article in root.iter("PubmedArticle"):
        pmid_el = article.find(".//PMID")
        if pmid_el is None or not (pmid_el.text or "").strip():
            continue
        pmid = pmid_el.text.strip()
        abstract_parts = []
        for at in article.findall(".//AbstractText"):
            label = at.get("Label")
            text = "".join(at.itertext()).strip()
            if not text:
                continue
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        if not abstract_parts:
            continue
        out.append((f"PubMed:{pmid}", "\n".join(abstract_parts)))
    return out


def _efetch_abstracts_text_fallback(text: str) -> list[tuple[str, str]]:
    """Fallback text-based parsing when XML is unavailable."""
    out: list[tuple[str, str]] = []
    blocks = text.split("PMID:")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        first = lines[0].strip()
        pmid = first.split()[0] if first else ""
        if not pmid or not pmid.isdigit():
            continue
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        if not body:
            continue
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
        for i, q in enumerate(queries):
            if i > 0:
                time.sleep(DELAY_BETWEEN_QUERIES)
            try:
                docs = fetch_abstracts_for_query(q, max_per_query, client=client)
                documents.extend(docs)
            except httpx.HTTPError as exc:
                logger.warning(
                    "Failed to fetch PubMed abstracts for query %r: %s",
                    q,
                    exc,
                )
                continue
    if not documents:
        return 0
    return index_documents(documents)
