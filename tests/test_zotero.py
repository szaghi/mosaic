"""Tests for mosaic.zotero — ZoteroClient (local and web mode)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mosaic.models import Paper
from mosaic.zotero import ZoteroClient, _paper_to_item, _parse_author


# ── helpers ───────────────────────────────────────────────────────────────────

def _paper(**kwargs) -> Paper:
    defaults = dict(
        title="Test Paper",
        authors=["Alice Smith", "Bob Jones"],
        year=2020,
        doi="10.1/test",
        journal="Nature",
        abstract="An abstract.",
        source="arXiv",
        pdf_url=None,
    )
    defaults.update(kwargs)
    return Paper(**defaults)


def _mock_response(json_data=None, status_code=200):
    m = MagicMock()
    m.status_code = status_code
    if json_data is not None:
        m.json.return_value = json_data
    m.raise_for_status = MagicMock()
    return m


# ── ZoteroClient construction ─────────────────────────────────────────────────

class TestZoteroClientConstruction:
    def test_local_mode_base_url(self):
        c = ZoteroClient()
        assert c._base == "http://localhost:23119/api/users/0"

    def test_local_mode_custom_port(self):
        c = ZoteroClient(port=9999)
        assert "9999" in c._base

    def test_web_mode_base_url(self):
        c = ZoteroClient(api_key="abc", user_id=42)
        assert c._base == "https://api.zotero.org/users/42"

    def test_web_mode_base_url_updates_after_discover(self):
        c = ZoteroClient(api_key="abc", user_id=0)
        assert "/users/0" in c._base
        c._user_id = 99
        assert "/users/99" in c._base

    def test_local_headers_no_auth(self):
        c = ZoteroClient()
        assert "Zotero-API-Key" not in c._headers

    def test_web_headers_include_key(self):
        c = ZoteroClient(api_key="mykey")
        assert c._headers["Zotero-API-Key"] == "mykey"

    def test_web_mode_property(self):
        assert ZoteroClient(api_key="k")._web_mode is True
        assert ZoteroClient()._web_mode is False


# ── is_reachable ──────────────────────────────────────────────────────────────

class TestIsReachable:
    def test_local_true_on_200(self):
        c = ZoteroClient()
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.get.return_value = _mock_response(status_code=200)
            assert c.is_reachable() is True

    def test_local_false_on_connection_error(self):
        c = ZoteroClient()
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.get.side_effect = Exception("refused")
            assert c.is_reachable() is False

    def test_web_true_on_200(self):
        c = ZoteroClient(api_key="k")
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.get.return_value = _mock_response(status_code=200)
            assert c.is_reachable() is True

    def test_web_false_on_401(self):
        c = ZoteroClient(api_key="bad")
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.get.return_value = _mock_response(status_code=403)
            assert c.is_reachable() is False

    def test_false_on_500(self):
        c = ZoteroClient()
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.get.return_value = _mock_response(status_code=500)
            assert c.is_reachable() is False


# ── discover_user_id ──────────────────────────────────────────────────────────

class TestDiscoverUserId:
    def test_returns_user_id_and_caches(self):
        c = ZoteroClient(api_key="mykey", user_id=0)
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.get.return_value = \
                _mock_response(json_data={"userID": 12345678, "key": "mykey"})
            uid = c.discover_user_id()
        assert uid == 12345678
        assert c._user_id == 12345678

    def test_noop_in_local_mode(self):
        c = ZoteroClient()
        assert c.discover_user_id() == 0

    def test_base_url_updated_after_discover(self):
        c = ZoteroClient(api_key="k", user_id=0)
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.get.return_value = \
                _mock_response(json_data={"userID": 99})
            c.discover_user_id()
        assert c._base == "https://api.zotero.org/users/99"


# ── ensure_collection ─────────────────────────────────────────────────────────

class TestEnsureCollection:
    def _collections_response(self, names: list[str]) -> list[dict]:
        return [{"data": {"key": f"KEY{i}", "name": n}} for i, n in enumerate(names)]

    def test_returns_existing_key(self):
        c = ZoteroClient()
        resp = _mock_response(json_data=self._collections_response(["Papers", "MyLib"]))
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.get.return_value = resp
            key = c.ensure_collection("MyLib")
        assert key == "KEY1"

    def test_creates_missing_collection(self):
        c = ZoteroClient()
        get_resp  = _mock_response(json_data=[])
        post_resp = _mock_response(json_data={"successful": {"0": {"key": "NEWKEY"}}})
        client_mock = MagicMock()
        client_mock.get.return_value  = get_resp
        client_mock.post.return_value = post_resp
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = client_mock
            key = c.ensure_collection("New")
        assert key == "NEWKEY"

    def test_post_payload_has_name(self):
        c = ZoteroClient()
        get_resp  = _mock_response(json_data=[])
        post_resp = _mock_response(json_data={"successful": {"0": {"key": "K"}}})
        client_mock = MagicMock()
        client_mock.get.return_value  = get_resp
        client_mock.post.return_value = post_resp
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = client_mock
            c.ensure_collection("MyCol")
        payload = client_mock.post.call_args.kwargs["json"]
        assert payload[0]["name"] == "MyCol"


# ── add_papers ────────────────────────────────────────────────────────────────

class TestAddPapers:
    def test_returns_item_keys(self):
        c = ZoteroClient()
        resp = _mock_response(json_data={
            "successful": {"0": {"key": "AAAA"}, "1": {"key": "BBBB"}},
            "failed": {},
        })
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.post.return_value = resp
            keys = c.add_papers([_paper(), _paper(doi="10.2/b")])
        assert keys == ["AAAA", "BBBB"]

    def test_empty_string_for_failed_item(self):
        c = ZoteroClient()
        resp = _mock_response(json_data={
            "successful": {"0": {"key": "AAAA"}},
            "failed": {"1": {"code": 413, "message": "too large"}},
        })
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.post.return_value = resp
            keys = c.add_papers([_paper(), _paper(doi="10.2/b")])
        assert keys[0] == "AAAA"
        assert keys[1] == ""

    def test_sends_collection_key_in_payload(self):
        c = ZoteroClient()
        resp = _mock_response(json_data={"successful": {"0": {"key": "K"}}, "failed": {}})
        mock_client = MagicMock()
        mock_client.post.return_value = resp
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = mock_client
            c.add_papers([_paper()], collection_key="COLLKEY")
        payload = mock_client.post.call_args.kwargs["json"]
        assert "COLLKEY" in payload[0]["collections"]

    def test_chunks_at_50(self):
        c = ZoteroClient()
        papers = [_paper(doi=f"10.1/{i}") for i in range(110)]

        def _resp_for_chunk(*args, **kwargs):
            chunk = kwargs.get("json", [])
            successful = {str(i): {"key": f"K{i}"} for i in range(len(chunk))}
            return _mock_response(json_data={"successful": successful, "failed": {}})

        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.post.side_effect = _resp_for_chunk
            keys = c.add_papers(papers)
        # 3 POST calls (50+50+10)
        assert mock_cls.return_value.__enter__.return_value.post.call_count == 3
        assert len(keys) == 110
        assert all(k for k in keys)  # all non-empty


# ── attach_pdf ────────────────────────────────────────────────────────────────

class TestAttachPdf:
    def test_local_mode_posts_linked_file(self, tmp_path):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF")
        c = ZoteroClient()
        resp = _mock_response(json_data={"successful": {"0": {"key": "ATT"}}, "failed": {}})
        mock_client = MagicMock()
        mock_client.post.return_value = resp
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value = mock_client
            result = c.attach_pdf("ITEM1", pdf)
        assert result is True
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload[0]["linkMode"] == "linked_file"
        assert payload[0]["parentItem"] == "ITEM1"

    def test_web_mode_returns_false(self, tmp_path):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF")
        c = ZoteroClient(api_key="k", user_id=1)
        result = c.attach_pdf("ITEM1", pdf)
        assert result is False

    def test_local_returns_false_on_error(self, tmp_path):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF")
        c = ZoteroClient()
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.return_value.post.side_effect = Exception("conn")
            result = c.attach_pdf("ITEM1", pdf)
        assert result is False


# ── _paper_to_item ────────────────────────────────────────────────────────────

class TestPaperToItem:
    def test_maps_basic_fields(self):
        p = _paper(title="T", year=2021, doi="10.1/x", abstract="A", journal="J", source="DOAJ")
        item = _paper_to_item(p)
        assert item["title"] == "T"
        assert item["date"] == "2021"
        assert item["DOI"] == "10.1/x"
        assert item["abstractNote"] == "A"
        assert item["publicationTitle"] == "J"

    def test_arxiv_maps_to_preprint(self):
        p = _paper(source="arXiv")
        assert _paper_to_item(p)["itemType"] == "preprint"

    def test_non_arxiv_maps_to_journal_article(self):
        p = _paper(source="DOAJ")
        assert _paper_to_item(p)["itemType"] == "journalArticle"

    def test_url_falls_back_to_doi_url(self):
        p = _paper(doi="10.1/x", source="DOAJ")
        p.url = None
        item = _paper_to_item(p)
        assert item["url"] == "https://doi.org/10.1/x"

    def test_collection_key_included(self):
        p = _paper()
        item = _paper_to_item(p, collection_key="MYCOL")
        assert "MYCOL" in item["collections"]

    def test_no_collection_key_no_collections_field(self):
        p = _paper()
        item = _paper_to_item(p)
        assert "collections" not in item

    def test_empty_journal_no_publication_title(self):
        p = _paper(journal=None)
        item = _paper_to_item(p)
        assert "publicationTitle" not in item

    def test_creators_mapped(self):
        p = _paper(authors=["Smith, Alice", "Bob Jones"])
        item = _paper_to_item(p)
        assert item["creators"][0]["lastName"] == "Smith"
        assert item["creators"][1]["lastName"] == "Jones"


# ── _parse_author ─────────────────────────────────────────────────────────────

class TestParseAuthor:
    def test_last_comma_first(self):
        r = _parse_author("Vaswani, Ashish")
        assert r["lastName"] == "Vaswani"
        assert r["firstName"] == "Ashish"

    def test_first_last_space(self):
        r = _parse_author("Ashish Vaswani")
        assert r["firstName"] == "Ashish"
        assert r["lastName"] == "Vaswani"

    def test_multi_word_first_name(self):
        r = _parse_author("Geoffrey E. Hinton")
        assert r["firstName"] == "Geoffrey E."
        assert r["lastName"] == "Hinton"

    def test_single_word(self):
        r = _parse_author("Einstein")
        assert r["lastName"] == "Einstein"
        assert r["firstName"] == ""

    def test_empty_string(self):
        r = _parse_author("")
        assert r["lastName"] == ""
        assert r["firstName"] == ""

    def test_creator_type_is_author(self):
        assert _parse_author("Test Name")["creatorType"] == "author"
