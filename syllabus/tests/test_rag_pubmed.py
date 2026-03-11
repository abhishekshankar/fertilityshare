"""Tests for PubMed RAG ingestion (PRD T-012)."""

from unittest.mock import MagicMock, patch

from syllabus.rag.pubmed import (
    DEFAULT_QUERIES,
    _efetch_abstracts,
    _esearch,
    fetch_abstracts_for_query,
    index_pubmed,
)


def test_efetch_abstracts_xml_parsing():
    """Parse efetch XML response into (source_id, text) pairs."""
    xml_text = """<?xml version="1.0" ?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <Abstract>
          <AbstractText>Abstract text here. Multiple lines.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>67890</PMID>
      <Article>
        <Abstract>
          <AbstractText>Single line abstract.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""
    mock_resp = MagicMock()
    mock_resp.text = xml_text
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.request.return_value = mock_resp
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
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.request.return_value = mock_response
    ids = _esearch("IVF", 10, mock_client)
    assert ids == ["1", "2", "3"]


def test_default_queries_non_empty():
    """Default fertility queries are defined."""
    assert len(DEFAULT_QUERIES) >= 5
    assert any("IVF" in q for q in DEFAULT_QUERIES)
    assert any("PCOS" in q for q in DEFAULT_QUERIES)


def test_fetch_abstracts_for_query_creates_and_closes_client(monkeypatch):
    """fetch_abstracts_for_query creates its own client and closes it when no client is provided."""
    xml_text = """<?xml version="1.0" ?><PubmedArticleSet>
      <PubmedArticle><MedlineCitation><PMID>111</PMID>
        <Article><Abstract><AbstractText>Body.</AbstractText></Abstract></Article>
      </MedlineCitation></PubmedArticle></PubmedArticleSet>"""
    esearch_resp = MagicMock()
    esearch_resp.json.return_value = {"esearchresult": {"idlist": ["111"]}}
    esearch_resp.status_code = 200
    esearch_resp.raise_for_status = MagicMock()
    efetch_resp = MagicMock()
    efetch_resp.text = xml_text
    efetch_resp.status_code = 200
    efetch_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.request.side_effect = [esearch_resp, efetch_resp]
    monkeypatch.setattr("syllabus.rag.pubmed.httpx.Client", lambda: mock_client)
    monkeypatch.setattr("syllabus.rag.pubmed.time.sleep", lambda _: None)
    result = fetch_abstracts_for_query("test query", 10)
    assert len(result) == 1
    assert result[0][0] == "PubMed:111"
    mock_client.close.assert_called_once()


def test_fetch_abstracts_for_query_empty_ids(monkeypatch):
    """fetch_abstracts_for_query returns empty list when no PMIDs found."""
    esearch_resp = MagicMock()
    esearch_resp.json.return_value = {"esearchresult": {"idlist": []}}
    esearch_resp.status_code = 200
    esearch_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.request.return_value = esearch_resp
    monkeypatch.setattr("syllabus.rag.pubmed.httpx.Client", lambda: mock_client)
    monkeypatch.setattr("syllabus.rag.pubmed.time.sleep", lambda _: None)
    result = fetch_abstracts_for_query("no results", 10)
    assert result == []
    mock_client.close.assert_called_once()


def test_index_pubmed_calls_index_documents(monkeypatch):
    """index_pubmed builds documents and calls index_documents."""
    xml_text = """<?xml version="1.0" ?><PubmedArticleSet>
      <PubmedArticle><MedlineCitation><PMID>123</PMID>
        <Article><Abstract><AbstractText>Abstract.</AbstractText></Abstract></Article>
      </MedlineCitation></PubmedArticle></PubmedArticleSet>"""
    mock_index = MagicMock(return_value=42)
    monkeypatch.setattr("syllabus.rag.pubmed.index_documents", mock_index)
    mock_esearch_resp = MagicMock()
    mock_esearch_resp.json.return_value = {"esearchresult": {"idlist": ["123"]}}
    mock_esearch_resp.status_code = 200
    mock_esearch_resp.raise_for_status = MagicMock()
    mock_efetch_resp = MagicMock()
    mock_efetch_resp.status_code = 200
    mock_efetch_resp.raise_for_status = MagicMock()
    mock_efetch_resp.text = xml_text
    mock_client_instance = MagicMock()
    mock_client_instance.request.side_effect = [mock_esearch_resp, mock_efetch_resp]
    mock_cm = MagicMock()
    mock_cm.__enter__ = lambda s: mock_client_instance
    mock_cm.__exit__ = lambda s, *a: None
    with (
        patch("syllabus.rag.pubmed.httpx.Client", return_value=mock_cm),
        patch("syllabus.rag.pubmed.time.sleep"),
    ):
        n = index_pubmed(queries=["dummy"], max_per_query=1)
    assert n == 42
    mock_index.assert_called_once()
    call_args = mock_index.call_args[0][0]
    assert isinstance(call_args, list)
    assert len(call_args) >= 1
    assert call_args[0][0].startswith("PubMed:")
