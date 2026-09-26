"""Zotero client: key never in URLs, user-id discovery, local write errors, item types."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mosaic.models import Paper
from mosaic.zotero import _KEYS_URL, ZoteroClient, _paper_to_item


def _resp(json_data=None, status_code=200):
    import httpx

    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data if json_data is not None else {}
    if status_code >= 400:
        req = httpx.Request("POST", "http://localhost")
        m.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=req, response=httpx.Response(status_code, request=req)
        )
    else:
        m.raise_for_status = MagicMock()
    return m


def _client_cm(mock_client):
    cm = MagicMock()
    cm.__enter__.return_value = mock_client
    cm.__exit__.return_value = False
    return cm


class TestKeyNotInUrl:
    def test_keys_url_has_no_placeholder(self):
        assert "{" not in _KEYS_URL
        assert _KEYS_URL.endswith("/keys/current")

    def test_is_reachable_sends_key_in_header_only(self):
        mock = MagicMock()
        mock.get.return_value = _resp({"userID": 1})
        with patch("mosaic.zotero.httpx.Client", return_value=_client_cm(mock)):
            assert ZoteroClient(api_key="SECRETKEY").is_reachable()
        url = mock.get.call_args.args[0]
        assert "SECRETKEY" not in url
        assert mock.get.call_args.kwargs["headers"]["Zotero-API-Key"] == "SECRETKEY"

    def test_discover_sends_key_in_header_only(self):
        mock = MagicMock()
        mock.get.return_value = _resp({"userID": 4242})
        with patch("mosaic.zotero.httpx.Client", return_value=_client_cm(mock)):
            c = ZoteroClient(api_key="SECRETKEY")
            assert c.discover_user_id() == 4242
        assert "SECRETKEY" not in mock.get.call_args.args[0]
        assert c.user_id == 4242


class TestLazyUserIdDiscovery:
    def test_add_papers_discovers_user_id_first(self):
        mock = MagicMock()
        mock.get.return_value = _resp({"userID": 99})
        mock.post.return_value = _resp({"successful": {"0": {"key": "K1"}}})
        with patch("mosaic.zotero.httpx.Client", return_value=_client_cm(mock)):
            c = ZoteroClient(api_key="k")  # user_id defaults to 0
            keys = c.add_papers([Paper(title="T")])
        assert keys == ["K1"]
        assert "/users/99/items" in mock.post.call_args.args[0]
        assert c.user_id == 99

    def test_known_user_id_skips_discovery(self):
        mock = MagicMock()
        mock.post.return_value = _resp({"successful": {"0": {"key": "K1"}}})
        with patch("mosaic.zotero.httpx.Client", return_value=_client_cm(mock)):
            ZoteroClient(api_key="k", user_id=7).add_papers([Paper(title="T")])
        mock.get.assert_not_called()
        assert "/users/7/items" in mock.post.call_args.args[0]


class TestLocalWriteRefused:
    @pytest.mark.parametrize("status", [401, 403, 404, 501])
    def test_add_papers_raises_actionable_runtime_error(self, status):
        mock = MagicMock()
        mock.post.return_value = _resp(status_code=status)
        with patch("mosaic.zotero.httpx.Client", return_value=_client_cm(mock)):
            with pytest.raises(RuntimeError, match="--zotero-key"):
                ZoteroClient().add_papers([Paper(title="T")])

    def test_create_collection_raises_actionable_runtime_error(self):
        mock = MagicMock()
        mock.get.return_value = _resp([])
        mock.post.return_value = _resp(status_code=403)
        with patch("mosaic.zotero.httpx.Client", return_value=_client_cm(mock)):
            with pytest.raises(RuntimeError, match="local API"):
                ZoteroClient().ensure_collection("New")

    def test_web_mode_errors_stay_http_errors(self):
        import httpx

        mock = MagicMock()
        mock.post.return_value = _resp(status_code=403)
        with patch("mosaic.zotero.httpx.Client", return_value=_client_cm(mock)):
            with pytest.raises(httpx.HTTPStatusError):
                ZoteroClient(api_key="k", user_id=1).add_papers([Paper(title="T")])


class TestPreprintItems:
    def test_biorxiv_medrxiv_source_is_preprint(self):
        item = _paper_to_item(Paper(title="T", source="bioRxiv/medRxiv"))
        assert item["itemType"] == "preprint"
        assert item["repository"] == "bioRxiv/medRxiv"

    def test_preprint_has_no_publication_title(self):
        p = Paper(title="T", source="arXiv", arxiv_id="1706.03762", journal="NeurIPS")
        item = _paper_to_item(p)
        assert "publicationTitle" not in item
        assert item["archiveID"] == "arXiv:1706.03762"
        assert "NeurIPS" in item["extra"]

    def test_journal_article_keeps_publication_title(self):
        item = _paper_to_item(Paper(title="T", source="Crossref", journal="Nature"))
        assert item["itemType"] == "journalArticle"
        assert item["publicationTitle"] == "Nature"
        assert "repository" not in item
