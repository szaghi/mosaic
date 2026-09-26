"""Web UI tests for security hardening, CLI parity and the fixes from the code review."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from mosaic.models import Paper


@pytest.fixture
def base_cfg(tmp_path):
    return {
        "db_path": str(tmp_path / "test.db"),
        "download_dir": str(tmp_path / "downloads"),
        "filename_pattern": "{year}_{source}_{author}_{title}",
        "sources": {},
        "unpaywall": {"email": ""},
        "zotero": {},
        "llm": {},
        "rag": {},
    }


def _make_app(cfg, **kwargs):
    from mosaic.ui import create_app

    with patch("mosaic.config.load", return_value=cfg):
        app = create_app(**kwargs)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def app(base_cfg):
    app = _make_app(base_cfg)
    yield app
    app.config["MOSAIC_CACHE"].close()


@pytest.fixture
def client(app):
    return app.test_client()


def _cache(app):
    return app.config["MOSAIC_CACHE"]


def _wait(app, html: bytes, route: str):
    """Extract the polled job id for *route* from *html* and wait for it."""
    match = re.search(rf"{re.escape(route)}/([0-9a-f]+)".encode(), html)
    assert match, html
    job_id = match.group(1).decode()
    job = app.config["JOB_MANAGER"].get(job_id)
    assert job is not None and job.wait(timeout=10)
    return job_id


def _paper(**kw):
    defaults = {"title": "Test Paper", "doi": "10.1234/test", "source": "arXiv", "year": 2024}
    defaults.update(kw)
    return Paper(**defaults)


# ── Security ─────────────────────────────────────────────────────────────────


class TestHostAndOriginChecks:
    def test_foreign_host_rejected(self, client):
        resp = client.get("/config", headers={"Host": "attacker.example:5555"})
        assert resp.status_code == 403

    def test_loopback_hosts_allowed(self, client):
        for host in ("localhost:5555", "127.0.0.1:5555", "[::1]:5555"):
            assert client.get("/", headers={"Host": host}).status_code == 200

    def test_explicit_bind_host_allowed(self, base_cfg):
        client = _make_app(base_cfg, bind_host="192.168.1.20").test_client()
        assert client.get("/", headers={"Host": "192.168.1.20:5555"}).status_code == 200
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 403

    def test_wildcard_bind_accepts_any_host(self, base_cfg):
        client = _make_app(base_cfg, bind_host="0.0.0.0").test_client()
        assert client.get("/", headers={"Host": "my-lab-server:5555"}).status_code == 200

    def test_cross_origin_post_blocked(self, client):
        with patch("mosaic.config.save") as save:
            resp = client.post(
                "/config",
                data={"_llm_section": "1", "llm_base_url": "https://evil.example/v1"},
                headers={"Origin": "https://evil.example"},
            )
        assert resp.status_code == 403
        save.assert_not_called()

    def test_cross_site_fetch_metadata_blocked(self, client):
        resp = client.post("/rag/chat/clear", headers={"Sec-Fetch-Site": "cross-site"})
        assert resp.status_code == 403

    def test_same_origin_post_allowed(self, client):
        resp = client.post(
            "/search",
            data={"query": ""},
            headers={"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"},
        )
        assert resp.status_code == 200

    def test_security_headers(self, client):
        resp = client.get("/")
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"


class TestConfigSecrets:
    def _seed(self, **overrides):
        import copy

        import mosaic.config as cfg_mod

        cfg = copy.deepcopy(cfg_mod._DEFAULTS)
        cfg["llm"]["api_key"] = "sk-SECRET-123"
        cfg["sources"]["core"]["api_key"] = "CORE-SECRET"
        cfg.update(overrides)
        cfg_mod.save(cfg)
        return cfg_mod

    def test_secrets_not_rendered(self, client):
        self._seed()
        html = client.get("/config").data
        assert b"sk-SECRET-123" not in html and b"CORE-SECRET" not in html
        assert b"clear_llm_api_key" in html  # "remove saved value" option offered

    def test_blank_keeps_and_clear_removes(self, client):
        cfg_mod = self._seed()
        client.post(
            "/config",
            data={"_llm_section": "1", "llm_api_key": "", "clear_core_key": "on"},
            headers={"HX-Request": "true"},
        )
        cfg = cfg_mod.load()
        assert cfg["llm"]["api_key"] == "sk-SECRET-123"
        assert cfg["sources"]["core"]["api_key"] == ""

    def test_zotero_key_discovers_user_id(self, client):
        cfg_mod = self._seed()
        with patch("mosaic.zotero.ZoteroClient") as zc:
            zc.return_value.discover_user_id.return_value = 99
            client.post("/config", data={"zotero_key": "ZKEY"}, headers={"HX-Request": "true"})
        assert cfg_mod.load()["zotero"] == {"api_key": "ZKEY", "user_id": 99}

    def test_invalid_numbers_are_reported(self, client):
        self._seed()
        resp = client.post(
            "/config",
            data={"rate_limit_delay": "fast", "_rag_section": "1", "rag_top_k": "0"},
            headers={"HX-Request": "true"},
        )
        assert b"Configuration saved" in resp.data
        assert b"not a valid number" in resp.data and b"rag_top_k" in resp.data

    def test_rag_parity_fields_saved(self, client):
        cfg_mod = self._seed()
        client.post(
            "/config",
            data={
                "_rag_section": "1",
                "rag_chunk_size": "256",
                "rag_chunk_overlap": "32",
                "rag_citations_enabled": "on",
            },
            headers={"HX-Request": "true"},
        )
        rag = cfg_mod.load()["rag"]
        assert (rag["chunk_size"], rag["chunk_overlap"]) == (256, 32)
        assert rag["citations"]["enabled"] is True
        assert rag["full_text_index"] is False  # unchecked box

    def test_db_path_change_swaps_cache(self, client, app, tmp_path):
        self._seed()
        new_db = tmp_path / "moved" / "cache.db"
        client.post("/config", data={"db_path": str(new_db)}, headers={"HX-Request": "true"})
        assert app.config["MOSAIC_CACHE"]._db_path == str(new_db)


class TestUntrustedUrls:
    def test_javascript_urls_not_linked(self, client, app):
        paper = _paper(pdf_url="javascript:alert(1)", url="JavaScript:alert(2)")
        _cache(app).save(paper)
        html = client.get(f"/paper/{paper.uid}").data
        assert not re.search(rb'href="\s*javascript:', html, re.IGNORECASE)


# ── Search / results parity ──────────────────────────────────────────────────


class TestLocalSearchModes:
    def test_cached_results_are_exportable_as_ris(self, client, app):
        _cache(app).save(_paper(title="Cached transformer paper"))
        resp = client.post("/search", data={"query": "transformer", "mode": "cached"})
        job_id = re.search(rb"/export/([0-9a-f]+)", resp.data).group(1).decode()
        # results live on a JobManager job, so they are purged like any other
        assert app.config["JOB_MANAGER"].get(job_id) is not None
        export = client.get(f"/export/{job_id}?format=ris")
        assert export.status_code == 200
        assert "mosaic_results.ris" in export.headers["Content-Disposition"]
        assert b"TY  -" in export.data

    def test_unknown_export_format(self, client, app):
        _cache(app).save(_paper(title="Cached transformer paper"))
        resp = client.post("/search", data={"query": "transformer", "mode": "cached"})
        job_id = re.search(rb"/export/([0-9a-f]+)", resp.data).group(1).decode()
        assert client.get(f"/export/{job_id}?format=exe").status_code == 400

    def test_semantic_mode_shows_similarity(self, client):
        hit = _paper(title="Semantic hit")
        hit.relevance_score = 0.87
        with patch("mosaic.rag.semantic_search", return_value=[hit]) as sem:
            resp = client.post(
                "/search", data={"query": "q", "mode": "semantic", "downloaded_only": "on"}
            )
        assert sem.call_args.kwargs["downloaded_only"] is True
        assert b"Sim." in resp.data and b"0.87" in resp.data

    def test_semantic_errors_are_shown(self, client):
        with patch("mosaic.rag.semantic_search", side_effect=RuntimeError("No vector index")):
            resp = client.post("/search", data={"query": "q", "mode": "semantic"})
        assert b"No vector index" in resp.data

    def test_invalid_field_rejected(self, client):
        resp = client.post("/search", data={"query": "q", "field": "body"})
        assert b"Invalid field" in resp.data


class TestNetworkSearch:
    def test_custom_source_selectable_and_results_processed(self, client, app):
        src = MagicMock()
        src.name = "My Repo"
        papers = [
            _paper(title="b", doi="10.1/b", year=2020),
            _paper(title="a", doi="10.1/a", year=2023),
        ]
        with (
            patch("mosaic.ui.routes.build_sources", return_value=[src]),
            patch("mosaic.ui.routes.source_choices", return_value={"myrepo": "My Repo"}),
            patch("mosaic.ui.routes.search_all", return_value=papers) as search,
        ):
            resp = client.post(
                "/search",
                data={"query": "q", "sources": ["myrepo"], "_has_sources": "1", "sort_by": "year"},
            )
            _wait(app, resp.data, "/search/status")
        assert search.call_args.args[0] == [src]
        status = client.get(re.search(rb'hx-get="([^"]+)"', resp.data).group(1).decode())
        assert status.data.index(b">a<") < status.data.index(b">b<")  # sorted by year
        # saved to the cache and logged for History
        assert _cache(app).get_by_uid("doi:10.1/a") is not None
        assert _cache(app).list_searches()[0]["query"] == "q"


class TestSimilar:
    def test_paper_not_found_message(self, client, app):
        with patch(
            "mosaic.ui.routes._run_similar", return_value={"seed_title": None, "papers": []}
        ):
            resp = client.post("/similar", data={"identifier": "10.9/none"})
            _wait(app, resp.data, "/similar/status")
            status = client.get(re.search(rb'hx-get="([^"]+)"', resp.data).group(1).decode())
        assert b"Paper not found" in status.data


# ── Detail page: citation ────────────────────────────────────────────────────


class TestCite:
    def test_bibtex_citation(self, client, app):
        paper = _paper(authors=["Ada Lovelace"])
        _cache(app).save(paper)
        resp = client.get(f"/cite/{paper.uid}?style=bibtex")
        assert b"@" in resp.data and b"Test Paper" in resp.data

    def test_unknown_style(self, client, app):
        paper = _paper()
        _cache(app).save(paper)
        assert b"Unknown style" in client.get(f"/cite/{paper.uid}?style=ieee-ish").data


# ── RAG ──────────────────────────────────────────────────────────────────────


class TestRagIndex:
    def test_index_job_handles_three_tuple(self, client, app):
        """Regression: the UI unpacked 2 values from index_papers' 3-tuple."""
        _cache(app).save(_paper())
        with patch("mosaic.rag.index_papers", return_value=(1, 0, 1)) as idx:
            resp = client.post("/rag/index", data={"batch_size": "32"})
            _wait(app, resp.data, "/rag/index/status")
        assert idx.call_args.kwargs["batch_size"] == 32
        status = client.get(re.search(rb'hx-get="([^"]+)"', resp.data).group(1).decode())
        assert b"1 paper(s) newly indexed" in status.data
        assert b"1 full-text" in status.data

    def test_index_subset_by_query(self, client, app):
        _cache(app).save(_paper(title="Alpha", doi="10.1/a"))
        _cache(app).save(_paper(title="Beta", doi="10.1/b"))
        with patch("mosaic.rag.index_papers", return_value=(1, 0, 0)) as idx:
            resp = client.post("/rag/index", data={"query": "Alpha"})
            _wait(app, resp.data, "/rag/index/status")
        assert [p.title for p in idx.call_args.args[0]] == ["Alpha"]


class TestRagAsk:
    def test_invalid_mode_and_year(self, client):
        assert b"Unknown mode" in client.post("/rag/ask", data={"query": "q", "mode": "x"}).data
        assert b"Invalid year" in client.post("/rag/ask", data={"query": "q", "year": "20x"}).data

    def test_answer_can_be_downloaded(self, client, app):
        paper = _paper(authors=["A B"])
        with patch("mosaic.rag.ask", return_value=("The **answer**", [paper])):
            resp = client.post("/rag/ask", data={"query": "Why?", "show_sources": "on"})
            job_id = _wait(app, resp.data, "/rag/ask/status")
        status = client.get(f"/rag/ask/status/{job_id}")
        assert b"The **answer**" in status.data and b"Source papers" in status.data
        md = client.get(f"/rag/ask/export/{job_id}?format=md")
        assert md.data.startswith(b"# Why?") and b"Test Paper" in md.data

    def test_subset_with_no_match_passes_empty_prefilter(self, client, app):
        with patch("mosaic.rag.ask", return_value=("none", [])) as ask:
            resp = client.post("/rag/ask", data={"query": "q", "subset_query": "zzz-nothing"})
            _wait(app, resp.data, "/rag/ask/status")
        assert ask.call_args.kwargs["pre_filter"] == []


class TestRagChat:
    def _turn(self, client, app, question, answer, papers):
        with patch("mosaic.rag.chat_turn", return_value=(answer, papers)) as turn:
            resp = client.post("/rag/chat/send", data={"query": question, "mode": "synthesis"})
            job_id = _wait(app, resp.data, "/rag/chat/status")
            client.get(f"/rag/chat/status/{job_id}")
        return turn

    def test_history_is_sent_to_the_llm(self, client, app):
        client.get("/rag/chat")
        self._turn(client, app, "First?", "First answer", [_paper()])
        turn = self._turn(client, app, "Follow-up?", "Second answer", [_paper()])
        question, history = turn.call_args.args[:2]
        assert question == "Follow-up?"
        assert history == [
            {"role": "user", "content": "First?"},
            {"role": "assistant", "content": "First answer"},
        ]

    def test_turns_without_sources_are_not_replayed(self, client, app):
        client.get("/rag/chat")
        self._turn(client, app, "Nothing indexed?", "No indexed papers found.", [])
        turn = self._turn(client, app, "Next", "ok", [_paper()])
        assert turn.call_args.args[1] == []

    def test_sources_rendered_under_answer(self, client, app):
        client.get("/rag/chat")
        self._turn(client, app, "Q", "A", [_paper(title="Cited paper")])
        page = client.get("/rag/chat").data
        assert b"Sources (1)" in page and b"Cited paper" in page


# ── NotebookLM (issue #30) ───────────────────────────────────────────────────


class TestNotebook:
    def test_preflight_error_returned_immediately(self, client, app):
        with patch(
            "mosaic.notebooklm_bridge.preflight_error",
            return_value="NotebookLM is not authenticated. Run `notebooklm login`",
        ):
            resp = client.post("/notebook", data={"name": "NB", "query": "q"})
        assert b"notebooklm login" in resp.data
        assert b"hx-get" not in resp.data  # no job, no polling

    def test_status_reports_warnings(self, client, app):
        from mosaic.notebooklm_bridge import NotebookResult

        nb = NotebookResult(nb_id="nb-1", artifacts_skipped=["podcast"])
        result = {
            "ok": True,
            "nb_url": nb.url,
            "sources_added": 0,
            "queued": [],
            "warnings": nb.warnings(),
        }
        job_id = app.config["JOB_MANAGER"].register_done(result)
        html = client.get(f"/notebook/status/{job_id}").data
        assert b"Notebook created" in html
        assert b"notebook is empty" in html and b"podcast" in html

    def test_system_exit_in_job_does_not_poll_forever(self, client, app):
        with (
            patch("mosaic.notebooklm_bridge.preflight_error", return_value=None),
            patch("mosaic.ui.routes._run_notebook_from_query", side_effect=SystemExit(1)),
        ):
            resp = client.post("/notebook", data={"name": "NB", "query": "q"})
            _wait(app, resp.data, "/notebook/status")
        status = client.get(re.search(rb'hx-get="([^"]+)"', resp.data).group(1).decode())
        assert b"Notebook creation failed" in status.data
        assert b"hx-get" not in status.data


# ── Bulk, library, analysis ──────────────────────────────────────────────────


class TestBulk:
    def test_bulk_reuses_cache_and_reports(self, client, app, tmp_path):
        import io

        from mosaic.workflows import DownloadItem, DownloadReport

        report = DownloadReport([DownloadItem(_paper(), "fail")])
        with patch("mosaic.workflows.bulk_get", return_value=([_paper()], report)) as bulk:
            resp = client.post(
                "/bulk",
                data={"file": (io.BytesIO(b"doi\n10.1234/test\n"), "refs.csv"), "oa_only": "on"},
                content_type="multipart/form-data",
            )
            job_id = _wait(app, resp.data, "/bulk/status")
        assert bulk.call_args.args[0] == ["10.1234/test"]
        html = client.get(f"/bulk/status/{job_id}").data
        assert b"skipped (no OA copy)" in html


class TestLibrary:
    def test_library_lists_and_clears(self, client, app):
        _cache(app).save(_paper(title="Library paper"))
        page = client.get("/library").data
        assert b"Library paper" in page and b"Verify downloads" in page
        assert b"Tick the confirmation" in client.post("/library/clear").data
        assert _cache(app).count_papers() == 1
        client.post("/library/clear", data={"confirm": "on"})
        assert _cache(app).count_papers() == 0

    def test_library_export(self, client, app):
        _cache(app).save(_paper(title="Library paper"))
        resp = client.get("/library/export?format=bib")
        assert resp.status_code == 200 and b"Library paper" in resp.data


class TestAnalysis:
    def test_network_without_edges(self, client, app):
        resp = client.post("/network", data={})
        job_id = _wait(app, resp.data, "/network/status")
        assert b"No citation edges" in client.get(f"/network/status/{job_id}").data

    def test_compare_table_and_export(self, client, app):
        _cache(app).save(_paper(title="Compared paper"))

        def fake_compare(papers, dims, cfg, errors=None):
            errors.append("batch 2 failed")
            return [dict.fromkeys(dims, "x") for _ in papers]

        with patch("mosaic.compare.compare_papers", side_effect=fake_compare):
            resp = client.post("/compare", data={"dimensions": "method, dataset"})
            job_id = _wait(app, resp.data, "/compare/status")
        html = client.get(f"/compare/status/{job_id}").data
        assert b"Compared paper" in html and b"Dataset" in html and b"batch 2 failed" in html
        csv = client.get(f"/compare/export/{job_id}?format=csv")
        assert b"Compared paper" in csv.data


class TestRagPages:
    def test_configured_model_shown_before_first_index(self, base_cfg):
        base_cfg["rag"] = {"embedding_model": "nomic-embed-text"}
        client = _make_app(base_cfg).test_client()
        for url in ("/rag", "/rag/index"):
            html = client.get(url).data
            assert b"nomic-embed-text" in html
            assert b"Not configured" not in html


class TestAccessToken:
    def test_loopback_needs_no_token_by_default(self, client):
        assert client.get("/").status_code == 200

    def test_token_required_when_configured(self, base_cfg):
        client = _make_app(base_cfg, bind_host="0.0.0.0", access_token="s3cret").test_client()
        assert client.get("/").status_code == 401
        assert client.get("/?token=wrong").status_code == 401

    def test_token_in_url_sets_session_and_is_stripped(self, base_cfg):
        client = _make_app(base_cfg, bind_host="0.0.0.0", access_token="s3cret").test_client()
        resp = client.get("/library?q=graph&token=s3cret")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/library?q=graph"
        assert client.get("/config").status_code == 200  # session cookie now suffices

    def test_bearer_header_for_scripts(self, base_cfg):
        client = _make_app(base_cfg, bind_host="0.0.0.0", access_token="s3cret").test_client()
        headers = {"Authorization": "Bearer s3cret"}
        assert client.get("/", headers=headers).status_code == 200
        assert client.get("/", headers={"Authorization": "Bearer nope"}).status_code == 401
