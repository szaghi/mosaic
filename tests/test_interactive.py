"""Tests for interactive (headed) downloads and session health."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mosaic.auth as auth

PDF = b"%PDF-1.7 body"


class FakeResponse:
    def __init__(self, body: bytes, ctype: str):
        self._body = body
        self.headers = {"content-type": ctype}

    async def body(self) -> bytes:
        return self._body


class FakeDownload:
    def __init__(self, path: str):
        self._path = path

    async def path(self) -> str:
        return self._path


class FakePage:
    """Fires Playwright-style events when navigating to scripted URLs."""

    def __init__(self, script: dict):
        self.script = script  # url -> list of ("response", body, ctype) | ("download", path)
        self.handlers: dict = {}
        self.closed = False

    def on(self, event, fn):
        self.handlers[event] = fn

    async def goto(self, url, **kw):
        for ev in self.script.get(url, []):
            if ev[0] == "response":
                await self.handlers["response"](FakeResponse(ev[1], ev[2]))
            else:
                await self.handlers["download"](FakeDownload(ev[1]))

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, script: dict, later: list | None = None):
        self.script = script
        self.later = later or []  # events fired after a delay (the user acting)
        self.tasks: list[asyncio.Task] = []  # keep references so tasks are not GC'd
        self.page_handlers = []
        self.state = {
            "cookies": [{"name": "sd_session_id", "domain": ".x", "value": "new"}],
            "origins": [],
        }

    def on(self, event, fn):
        self.page_handlers.append(fn)

    async def new_page(self):
        page = FakePage(self.script)
        for fn in self.page_handlers:
            fn(page)
        for delay, ev in self.later:

            async def fire(ev=ev, delay=delay, page=page):
                await asyncio.sleep(delay)
                if ev[0] == "response":
                    await page.handlers["response"](FakeResponse(ev[1], ev[2]))
                else:
                    await page.handlers["download"](FakeDownload(ev[1]))

            self.tasks.append(asyncio.ensure_future(fire()))
        return page

    async def storage_state(self):
        return self.state


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    d = tmp_path / "sessions"
    d.mkdir()
    monkeypatch.setattr(auth, "_SESSIONS_DIR", d)
    return d


def _save_session(d, name, cookies):
    (d / f"{name}.json").write_text(json.dumps({"cookies": cookies, "origins": []}))
    (d / f"{name}.meta.json").write_text(
        json.dumps({"login_url": f"https://{name}.com", "domain": f"{name}.com"})
    )


def _run(context, items, pdf_link=None, **kw):
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    pw_cm = AsyncMock()
    pw_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    pw_cm.__aexit__ = AsyncMock(return_value=False)
    pw_module = MagicMock()
    pw_module.async_playwright = MagicMock(return_value=pw_cm)
    with (
        patch("mosaic.auth._require_playwright"),
        patch("mosaic.auth._launch_browser", AsyncMock(return_value=browser)) as launch,
        patch("mosaic.auth._find_pdf_url", AsyncMock(return_value=pdf_link)),
        patch.dict(sys.modules, {"playwright.async_api": pw_module}),
    ):
        out = asyncio.run(auth.interactive_download(items, **kw))
    assert launch.call_args.kwargs["headless"] is False
    return out


class TestSessionHealth:
    def test_fresh_stale_missing(self, sessions_dir):
        _save_session(sessions_dir, "elsevier", [])
        assert auth.session_health("elsevier") == "fresh"
        old = time.time() - 7 * 24 * 3600
        os.utime(sessions_dir / "elsevier.json", (old, old))
        assert auth.session_health("elsevier") == "stale"
        assert auth.session_health("nope") == "missing"

    def test_year_long_analytics_cookie_does_not_make_old_session_fresh(self, sessions_dir):
        """The bug behind the misleading green tick in `auth status`."""
        year = time.time() + 365 * 24 * 3600
        _save_session(
            sessions_dir, "springer", [{"name": "_ga", "domain": ".springer.com", "expires": year}]
        )
        old = time.time() - 200 * 24 * 3600
        os.utime(sessions_dir / "springer.json", (old, old))
        assert (
            auth.session_is_valid("springer") is True
        )  # legacy check, still used for availability
        assert auth.session_health("springer") == "stale"


class TestMergedState:
    def test_cookies_from_all_sessions_are_merged(self, sessions_dir):
        _save_session(
            sessions_dir, "elsevier", [{"name": "a", "domain": ".sciencedirect.com", "value": "1"}]
        )
        _save_session(
            sessions_dir, "springer", [{"name": "b", "domain": ".springer.com", "value": "2"}]
        )
        state, names = auth._merged_storage_state()
        assert sorted(names) == ["elsevier", "springer"]
        assert {c["name"] for c in state["cookies"]} == {"a", "b"}


class TestInteractiveDownload:
    def test_pdf_reached_automatically_is_saved(self, tmp_path, sessions_dir):
        ctx = FakeContext({"https://pub/pdf": [("response", PDF, "application/pdf")]})
        dest = str(tmp_path / "p.pdf")
        out = _run(
            ctx,
            [("10.1/a", "https://pub/landing", dest)],
            pdf_link="https://pub/pdf",
            auto_wait_s=1,
        )
        assert out == {"10.1/a": dest}
        with open(dest, "rb") as f:
            assert f.read() == PDF

    def test_user_action_download_is_captured(self, tmp_path, sessions_dir):
        """IOP-style: nothing automatic works; the user clicks Download in the window."""
        clicked = tmp_path / "user-download.bin"
        clicked.write_bytes(PDF)
        ctx = FakeContext({}, later=[(0.2, ("download", str(clicked)))])
        dest = str(tmp_path / "p.pdf")
        results = []
        out = _run(
            ctx,
            [("10.1088/x", "https://iop/landing", dest)],
            auto_wait_s=0.05,
            user_wait_s=5,
            on_result=lambda k, p: results.append((k, p)),
        )
        assert out == {"10.1088/x": dest}
        assert results == [("10.1088/x", dest)]

    def test_html_response_is_not_taken_for_a_pdf(self, tmp_path, sessions_dir):
        ctx = FakeContext(
            {"https://pub/landing": [("response", b"<html>captcha</html>", "application/pdf")]}
        )
        dest = str(tmp_path / "p.pdf")
        out = _run(ctx, [("k", "https://pub/landing", dest)], auto_wait_s=0.05, user_wait_s=0.1)
        assert out == {}
        assert not os.path.exists(dest)

    def test_login_written_back_only_after_a_successful_download(self, tmp_path, sessions_dir):
        _save_session(
            sessions_dir, "elsevier", [{"name": "sd_session_id", "domain": ".x", "value": "old"}]
        )
        before = (sessions_dir / "elsevier.json").read_text()

        ctx = FakeContext({})
        _run(
            ctx,
            [("k", "https://pub/landing", str(tmp_path / "a.pdf"))],
            auto_wait_s=0.05,
            user_wait_s=0.1,
        )
        assert (
            sessions_dir / "elsevier.json"
        ).read_text() == before  # nothing proven, nothing written

        ctx = FakeContext({"https://pub/landing": [("response", PDF, "application/pdf")]})
        _run(ctx, [("k", "https://pub/landing", str(tmp_path / "b.pdf"))], auto_wait_s=0.5)
        saved = json.loads((sessions_dir / "elsevier.json").read_text())
        assert saved["cookies"][0]["value"] == "new"
        assert oct((sessions_dir / "elsevier.json").stat().st_mode & 0o777) == "0o600"

    def test_leftover_pdf_from_previous_paper_is_not_reused(self, tmp_path, sessions_dir):
        ctx = FakeContext(
            {
                "https://a/landing": [
                    ("response", PDF, "application/pdf"),
                    ("response", PDF, "application/pdf"),
                ]
            }
        )
        out = _run(
            ctx,
            [
                ("a", "https://a/landing", str(tmp_path / "a.pdf")),
                ("b", "https://b/landing", str(tmp_path / "b.pdf")),
            ],
            auto_wait_s=0.05,
            user_wait_s=0.1,
        )
        assert set(out) == {"a"}


class TestGetInteractiveCli:
    def _invoke(self, tmp_path, tmp_cache, args, rescued: dict):
        from typer.testing import CliRunner

        from mosaic.cli import app
        from mosaic.models import Paper

        csv = tmp_path / "dois.csv"
        csv.write_text("doi\n10.1/a\n10.1/b\n")
        cfg = {
            "db_path": ":memory:",
            "download_dir": str(tmp_path / "dl"),
            "unpaywall": {"email": ""},
        }

        async def fake_interactive(items, on_result=None, **kw):
            out = {}
            for key, _landing, dest in items:
                path = dest if key in rescued else None
                if path:
                    out[key] = path
                if on_result:
                    on_result(key, path)
            return out

        with (
            patch("mosaic.cli.cfg_mod.load", return_value=cfg),
            patch("mosaic.cli.Cache", return_value=tmp_cache),
            patch(
                "mosaic.cite.paper_for_download",
                side_effect=lambda d, *a: Paper(title=f"T {d}", doi=d, year=2020),
            ),
            patch("mosaic.cli.dl_paper", return_value=None),
            patch("mosaic.auth.interactive_download", side_effect=fake_interactive) as interactive,
        ):
            result = CliRunner().invoke(app, ["get", "--from", str(csv), *args])
        return result, interactive

    def test_failures_retried_interactively_and_counted(self, tmp_path, tmp_cache):
        r, interactive = self._invoke(tmp_path, tmp_cache, ["--interactive"], rescued={"10.1/b"})
        assert r.exit_code == 0, r.output
        (items,) = interactive.call_args.args
        assert [k for k, _, _ in items] == ["10.1/a", "10.1/b"]
        assert "1 downloaded" in r.output and "1 failed" in r.output
        from mosaic.models import Paper

        assert tmp_cache.get_download(Paper(title="x", doi="10.1/b").uid)["status"] == "ok"

    def test_without_flag_no_browser_and_a_hint(self, tmp_path, tmp_cache):
        r, interactive = self._invoke(tmp_path, tmp_cache, [], rescued=set())
        interactive.assert_not_called()
        assert "--interactive" in r.output
