"""Tests for PubMed RAG ingestion (PRD T-012)."""

from unittest.mock import MagicMock, patch

from syllabus.rag.pubmed import (
    DEFAULT_QUERIES,
    _efetch_abstracts,
    _esearch,
    index_pubmed,
)


def test_efetch_abstracts_parsing():
    """Parse efetch-style text into (source_id, text) pairs."""
    text = """PMID: 12345
Title of the study.

Abstract text here. Multiple lines.
Second paragraph.

PMID: 67890
Another title.
Single line abstract.
"""
    mock_client = MagicMock()
    mock_client.get.return_value.raise_for_status = MagicMock()
    mock_client.get.return_value.text = text
    result = _efetch_abstracts(["12345", "67890"], mock_client)
    assert len(result) == 2
    assert result[0][0] == "PubMed:12345"
    assert "Abstract text here" in result[0][1]
    assert result[1][0] == "PubMed:67890"
    assert "Single line abstract" in result[1][1]


def test_esearch_returns_idlist():
    """ESearch mock returns PMID list."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"esearchresult": {"idlist": ["1", "2", "3"]}}
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    ids = _esearch("IVF", 10, mock_client)
    assert ids == ["1", "2", "3"]


def test_default_queries_non_empty():
    """Default fertility queries are defined."""
    assert len(DEFAULT_QUERIES) >= 5
    assert any("IVF" in q for q in DEFAULT_QUERIES)
    assert any("PCOS" in q for q in DEFAULT_QUERIES)


def test_index_pubmed_calls_index_documents(monkeypatch):
    """index_pubmed builds documents and calls index_documents."""
    mock_index = MagicMock(return_value=42)
    monkeypatch.setattr("syllabus.rag.pubmed.index_documents", mock_index)
    mock_esearch_resp = MagicMock()
    mock_esearch_resp.json.return_value = {"esearchresult": {"idlist": ["123"]}}
    mock_esearch_resp.raise_for_status = MagicMock()
    mock_efetch_resp = MagicMock()
    mock_efetch_resp.raise_for_status = MagicMock()
    mock_efetch_resp.text = "PMID: 123\nTitle.\nAbstract."
    mock_client_instance = MagicMock()
    mock_client_instance.get.side_effect = [mock_esearch_resp, mock_efetch_resp]
    mock_cm = MagicMock()
    mock_cm.__enter__ = lambda s: mock_client_instance
    mock_cm.__exit__ = lambda s, *a: None
    with patch("syllabus.rag.pubmed.httpx.Client", return_value=mock_cm):
        with patch("syllabus.rag.pubmed.time.sleep"):
            n = index_pubmed(queries=["dummy"], max_per_query=1)
    assert n == 42
    mock_index.assert_called_once()
    call_args = mock_index.call_args[0][0]
    assert isinstance(call_args, list)
    assert len(call_args) >= 1
    assert call_args[0][0].startswith("PubMed:")
