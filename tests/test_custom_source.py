"""Tests for the generic CustomSource."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from mosaic.sources.custom import CustomSource, _get_nested, _parse_year


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

class TestGetNested:
    def test_top_level_key(self):
        assert _get_nested({"a": 1}, "a") == 1

    def test_nested_key(self):
        assert _get_nested({"a": {"b": 2}}, "a.b") == 2

    def test_deeply_nested(self):
        assert _get_nested({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_key_returns_none(self):
        assert _get_nested({"a": 1}, "b") is None

    def test_missing_intermediate_returns_none(self):
        assert _get_nested({"a": {}}, "a.b.c") is None

    def test_non_dict_intermediate_returns_none(self):
        assert _get_nested({"a": 42}, "a.b") is None


class TestParseYear:
    def test_int(self):
        assert _parse_year(2023) == 2023

    def test_string_year(self):
        assert _parse_year("2020") == 2020

    def test_iso_date(self):
        assert _parse_year("2021-06-15") == 2021

    def test_none(self):
        assert _parse_year(None) is None

    def test_unparseable(self):
        assert _parse_year("no year here") is None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BASE_CFG = {
    "name": "TestSource",
    "url": "https://api.example.com/search",
    "method": "GET",
    "query_param": "q",
    "results_path": "results",
    "fields": {
        "title":    "title",
        "doi":      "doi",
        "year":     "year",
        "abstract": "abstract",
        "journal":  "journal",
        "pdf_url":  "pdf",
        "url":      "link",
        "authors":  "authors",
    },
}

_ITEM = {
    "title":    "A Test Paper",
    "doi":      "10.1234/test",
    "year":     2023,
    "abstract": "An abstract.",
    "journal":  "Test Journal",
    "pdf":      "https://example.com/paper.pdf",
    "link":     "https://example.com/paper",
    "authors":  ["Alice Smith", "Bob Jones"],
}


def _make_response(items: list) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"results": items}
    mock.raise_for_status = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# CustomSource.available()
# ---------------------------------------------------------------------------

class TestAvailable:
    def test_true_when_url_set(self):
        src = CustomSource(_BASE_CFG)
        assert src.available() is True

    def test_false_when_url_empty(self):
        src = CustomSource({**_BASE_CFG, "url": ""})
        assert src.available() is False


# ---------------------------------------------------------------------------
# CustomSource.search() — GET
# ---------------------------------------------------------------------------

class TestSearchGet:
    def _search(self, cfg_override=None, items=None):
        cfg = {**_BASE_CFG, **(cfg_override or {})}
        src = CustomSource(cfg)
        resp = _make_response(items if items is not None else [_ITEM])
        with patch("httpx.get", return_value=resp) as mock_get:
            papers = src.search("quantum computing", max_results=10)
        return papers, mock_get

    def test_returns_papers(self):
        papers, _ = self._search()
        assert len(papers) == 1
        assert papers[0].title == "A Test Paper"

    def test_get_method_used(self):
        _, mock_get = self._search()
        mock_get.assert_called_once()

    def test_query_in_params(self):
        _, mock_get = self._search()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "quantum computing"

    def test_custom_query_param(self):
        _, mock_get = self._search({"query_param": "search"})
        assert "search" in mock_get.call_args.kwargs["params"]

    def test_max_results_param_injected(self):
        _, mock_get = self._search({"max_results_param": "limit"})
        assert mock_get.call_args.kwargs["params"]["limit"] == 10

    def test_api_key_header_set(self):
        _, mock_get = self._search({
            "api_key": "secret",
            "api_key_header": "X-My-Key",
        })
        assert mock_get.call_args.kwargs["headers"]["X-My-Key"] == "secret"

    def test_no_api_key_no_extra_header(self):
        _, mock_get = self._search({"api_key": "", "api_key_header": "X-My-Key"})
        assert "X-My-Key" not in mock_get.call_args.kwargs["headers"]

    def test_respects_max_results(self):
        items = [dict(_ITEM, title=f"Paper {i}") for i in range(20)]
        papers, _ = self._search(items=items)
        assert len(papers) == 10

    def test_raw_query_used_when_filter_set(self):
        from mosaic.models import SearchFilters
        src = CustomSource(_BASE_CFG)
        resp = _make_response([_ITEM])
        with patch("httpx.get", return_value=resp) as mock_get:
            src.search("ignored", filters=SearchFilters(raw_query="title:quantum"))
        assert mock_get.call_args.kwargs["params"]["q"] == "title:quantum"


# ---------------------------------------------------------------------------
# CustomSource.search() — POST
# ---------------------------------------------------------------------------

class TestSearchPost:
    def _search_post(self, cfg_override=None):
        cfg = {**_BASE_CFG, "method": "POST", **(cfg_override or {})}
        src = CustomSource(cfg)
        resp = _make_response([_ITEM])
        with patch("httpx.post", return_value=resp) as mock_post:
            papers = src.search("deep learning", max_results=5)
        return papers, mock_post

    def test_post_method_used(self):
        _, mock_post = self._search_post()
        mock_post.assert_called_once()

    def test_query_in_body(self):
        _, mock_post = self._search_post()
        assert mock_post.call_args.kwargs["json"]["q"] == "deep learning"

    def test_max_results_in_body(self):
        _, mock_post = self._search_post({"max_results_param": "count"})
        assert mock_post.call_args.kwargs["json"]["count"] == 5


# ---------------------------------------------------------------------------
# CustomSource._parse() — field mapping
# ---------------------------------------------------------------------------

class TestParse:
    def _parse(self, item, cfg_override=None):
        cfg = {**_BASE_CFG, **(cfg_override or {})}
        src = CustomSource(cfg)
        return src._parse(item)

    def test_basic_fields(self):
        p = self._parse(_ITEM)
        assert p.title    == "A Test Paper"
        assert p.doi      == "10.1234/test"
        assert p.year     == 2023
        assert p.abstract == "An abstract."
        assert p.journal  == "Test Journal"
        assert p.pdf_url  == "https://example.com/paper.pdf"
        assert p.url      == "https://example.com/paper"
        assert p.source   == "TestSource"

    def test_authors_flat_array(self):
        p = self._parse(_ITEM)
        assert p.authors == ["Alice Smith", "Bob Jones"]

    def test_authors_array_of_objects(self):
        item = {**_ITEM, "contributors": [{"name": "Carol"}, {"name": "Dave"}]}
        p = self._parse(item, {
            "authors_path": "contributors",
            "authors_field": "name",
        })
        assert p.authors == ["Carol", "Dave"]

    def test_nested_field_mapping(self):
        item = {"title": "T", "meta": {"pub": "Nature"}}
        cfg = {**_BASE_CFG, "fields": {"title": "title", "journal": "meta.pub"}}
        p = self._parse(item, cfg)
        assert p.journal == "Nature"

    def test_year_from_date_string(self):
        item = {**_ITEM, "year": "2019-03-22"}
        p = self._parse(item)
        assert p.year == 2019

    def test_missing_field_is_none(self):
        item = {"title": "Only Title"}
        p = self._parse(item, {"fields": {"title": "title"}})
        assert p.doi is None
        assert p.year is None

    def test_non_list_results_returns_empty(self):
        src = CustomSource(_BASE_CFG)
        resp = MagicMock()
        resp.json.return_value = {"results": "not a list"}
        resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=resp):
            papers = src.search("test")
        assert papers == []

    def test_nested_results_path(self):
        src = CustomSource({**_BASE_CFG, "results_path": "data.items"})
        resp = MagicMock()
        resp.json.return_value = {"data": {"items": [_ITEM]}}
        resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=resp):
            papers = src.search("test")
        assert len(papers) == 1
