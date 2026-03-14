"""Tests for similar-paper discovery (OpenAlex + Semantic Scholar)."""

from unittest.mock import MagicMock, patch

from mosaic.similar import _oa_work_url, _similar_openalex, _ss_paper_id, find_similar


def make_response(text="", json_data=None, status_code=200):
    m = MagicMock()
    m.status_code = status_code
    m.text = text
    if json_data is not None:
        m.json.return_value = json_data
    m.raise_for_status = MagicMock()
    return m


# ── URL / ID helpers ──────────────────────────────────────────────────────────


class TestOaWorkUrl:
    def test_bare_doi(self):
        url = _oa_work_url("10.1234/test")
        assert url == "https://api.openalex.org/works/https://doi.org/10.1234/test"

    def test_doi_prefix(self):
        url = _oa_work_url("doi:10.1234/test")
        assert url == "https://api.openalex.org/works/https://doi.org/10.1234/test"

    def test_DOI_uppercase_prefix(self):
        url = _oa_work_url("DOI:10.1234/test")
        assert url == "https://api.openalex.org/works/https://doi.org/10.1234/test"

    def test_arxiv_prefix(self):
        url = _oa_work_url("arxiv:1706.03762")
        assert url == "https://api.openalex.org/works/https://arxiv.org/abs/1706.03762"

    def test_ARXIV_uppercase_prefix(self):
        url = _oa_work_url("ARXIV:1706.03762")
        assert url == "https://api.openalex.org/works/https://arxiv.org/abs/1706.03762"


class TestSsPaperId:
    def test_bare_doi(self):
        assert _ss_paper_id("10.1234/test") == "DOI:10.1234/test"

    def test_doi_prefix_stripped(self):
        assert _ss_paper_id("doi:10.1234/test") == "DOI:10.1234/test"

    def test_arxiv_prefix(self):
        assert _ss_paper_id("arxiv:1706.03762") == "ARXIV:1706.03762"

    def test_ARXIV_uppercase(self):
        assert _ss_paper_id("ARXIV:1706.03762") == "ARXIV:1706.03762"


# ── OpenAlex similar ──────────────────────────────────────────────────────────

_SEED_RESPONSE = {
    "id": "https://openalex.org/W2963403868",
    "title": "Attention Is All You Need",
    "related_works": [
        "https://openalex.org/W2741809807",
        "https://openalex.org/W2898294028",
    ],
}

_RELATED_RESPONSE = {
    "results": [
        {
            "id": "https://openalex.org/W2741809807",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "authorships": [{"author": {"display_name": "Jacob Devlin"}}],
            "publication_year": 2019,
            "doi": "https://doi.org/10.18653/v1/N19-1423",
            "ids": {},
            "abstract_inverted_index": None,
            "primary_location": {"source": {"display_name": "NAACL"}, "pdf_url": None},
            "best_oa_location": {"pdf_url": "https://arxiv.org/pdf/1810.04805"},
            "open_access": {"is_oa": True},
            "biblio": {},
            "cited_by_count": 50000,
        },
        {
            "id": "https://openalex.org/W2898294028",
            "title": "GPT-2: Language Models are Unsupervised Multitask Learners",
            "authorships": [{"author": {"display_name": "Alec Radford"}}],
            "publication_year": 2019,
            "doi": None,
            "ids": {},
            "abstract_inverted_index": None,
            "primary_location": {"source": {"display_name": "OpenAI"}, "pdf_url": None},
            "best_oa_location": None,
            "open_access": {"is_oa": False},
            "biblio": {},
            "cited_by_count": 20000,
        },
    ]
}


class TestSimilarOpenAlex:
    def test_returns_seed_title_and_papers(self):
        responses = [
            make_response(json_data=_SEED_RESPONSE),
            make_response(json_data=_RELATED_RESPONSE),
        ]
        with patch("mosaic.similar.httpx.get", side_effect=responses):
            seed_title, papers = _similar_openalex("10.48550/arXiv.1706.03762", max_results=10)

        assert seed_title == "Attention Is All You Need"
        assert len(papers) == 2
        assert papers[0].title == "BERT: Pre-training of Deep Bidirectional Transformers"
        assert papers[0].citation_count == 50000

    def test_404_returns_none_and_empty(self):
        resp = make_response(status_code=404)
        resp.raise_for_status = MagicMock()
        with patch("mosaic.similar.httpx.get", return_value=resp):
            seed_title, papers = _similar_openalex("10.0/notfound", max_results=10)

        assert seed_title is None
        assert papers == []

    def test_empty_related_works_returns_seed_title_only(self):
        seed = {**_SEED_RESPONSE, "related_works": []}
        with patch("mosaic.similar.httpx.get", return_value=make_response(json_data=seed)):
            seed_title, papers = _similar_openalex("10.48550/arXiv.1706.03762", max_results=10)

        assert seed_title == "Attention Is All You Need"
        assert papers == []

    def test_max_results_caps_ids_fetched(self):
        seed = {
            **_SEED_RESPONSE,
            "related_works": [f"https://openalex.org/W{i}" for i in range(20)],
        }
        captured = []

        def fake_get(url, **kwargs):
            captured.append((url, kwargs.get("params", {})))
            if "related_works" in str(kwargs.get("params", {})):
                return make_response(json_data=seed)
            return make_response(json_data={"results": []})

        with patch("mosaic.similar.httpx.get", side_effect=fake_get):
            _similar_openalex("10.1/x", max_results=5)

        # Second call filter should contain only 5 IDs
        batch_filter = captured[1][1].get("filter", "")
        assert batch_filter.count("|") == 4  # 5 IDs → 4 pipes


# ── find_similar (fan-out + dedup) ───────────────────────────────────────────


class TestFindSimilar:
    def test_no_ss_key_uses_oa_only(self):
        responses = [
            make_response(json_data=_SEED_RESPONSE),
            make_response(json_data=_RELATED_RESPONSE),
        ]
        with patch("mosaic.similar.httpx.get", side_effect=responses) as mock_get:
            seed_title, papers = find_similar("10.1/x", max_results=10)

        assert mock_get.call_count == 2  # seed lookup + batch fetch; no SS call
        assert seed_title == "Attention Is All You Need"
        assert len(papers) == 2

    def test_ss_key_merges_results(self):
        ss_rec_response = {
            "recommendedPapers": [
                {
                    "paperId": "zzz",
                    "title": "New Paper From SS",
                    "authors": [{"name": "Alice"}],
                    "year": 2021,
                    "abstract": None,
                    "externalIds": {"DOI": "10.9/new"},
                    "openAccessPdf": None,
                    "publicationVenue": None,
                    "journal": None,
                    "isOpenAccess": False,
                    "citationCount": 100,
                }
            ]
        }

        def fake_get(url, **kwargs):
            if "recommendations" in url:
                return make_response(json_data=ss_rec_response)
            if "related_works" in str(kwargs.get("params", {})):
                return make_response(json_data=_SEED_RESPONSE)
            return make_response(json_data=_RELATED_RESPONSE)

        with patch("mosaic.similar.httpx.get", side_effect=fake_get):
            _, papers = find_similar("10.1/x", max_results=10, ss_api_key="key123")

        titles = {p.title for p in papers}
        assert "New Paper From SS" in titles
        assert len(papers) == 3  # 2 from OA + 1 unique from SS

    def test_ss_deduplicates_overlapping_paper(self):
        """Same DOI from OA and SS → one result with best citation count."""
        # OA returns BERT with citation_count=50000
        # SS returns BERT with citation_count=55000 → should win
        ss_rec_response = {
            "recommendedPapers": [
                {
                    "paperId": "bert",
                    "title": "BERT: Pre-training of Deep Bidirectional Transformers",
                    "authors": [{"name": "Jacob Devlin"}],
                    "year": 2019,
                    "abstract": "BERT abstract",
                    "externalIds": {"DOI": "10.18653/v1/N19-1423"},
                    "openAccessPdf": None,
                    "publicationVenue": None,
                    "journal": None,
                    "isOpenAccess": True,
                    "citationCount": 55000,
                }
            ]
        }

        def fake_get(url, **kwargs):
            if "recommendations" in url:
                return make_response(json_data=ss_rec_response)
            if "related_works" in str(kwargs.get("params", {})):
                return make_response(json_data=_SEED_RESPONSE)
            return make_response(json_data=_RELATED_RESPONSE)

        with patch("mosaic.similar.httpx.get", side_effect=fake_get):
            _, papers = find_similar("10.1/x", max_results=10, ss_api_key="key")

        bert_papers = [p for p in papers if "BERT" in p.title]
        assert len(bert_papers) == 1
        assert bert_papers[0].citation_count == 55000
        assert bert_papers[0].abstract == "BERT abstract"
