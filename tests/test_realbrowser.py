"""Tests for the real-browser (``--auto``) download pass.

No network and no browser: the Playwright context is replaced by fake pages,
and the download folder is a real tmp directory so the watcher logic runs.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

import mosaic.realbrowser as rb
from mosaic.errors import DependencyError

PDF_BODY = b"%PDF-1.7 body " + b"x" * 200

ARTICLE = "https://www.sciencedirect.com/science/article/pii/S0021999109006068?via%3Dihub"
PDFFT = ARTICLE.split("?")[0] + "/pdfft?md5=z&pid=1-s2.0-S0021999109006068-main.pdf"
ASSET = "https://pdf.sciencedirectassets.com/272570/xx/main.pdf?X-Amz-Signature=z"
DOI = "10.1016/j.jcp.2009.10.045"
NAME = "1-s2.0-S0021999109006068-main.pdf"


@pytest.fixture(autouse=True)
def fake_playwright(monkeypatch):
    """A stub ``playwright.async_api``: CI has no browser extra, and ``connect`` is faked anyway."""

    class _Manager:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc):
            return False

    api = types.ModuleType("playwright.async_api")
    api.async_playwright = _Manager
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", api)


# ── pure helpers ─────────────────────────────────────────────────────────────


def test_extract_pii():
    assert rb.extract_pii(ARTICLE) == "S0021999109006068"
    assert rb.extract_pii("https://linkinghub.elsevier.com/retrieve/pii/AB00112233") == "AB00112233"
    assert rb.extract_pii("not a url") is None


def test_name_ids():
    url = ARTICLE
    ids = rb._name_ids(DOI, url)
    assert "s0021999109006068" in ids
    assert "jjcp200910045" in ids  # the DOI suffix of the key


def test_signed_asset_url_unescapes():
    html = (
        'window.location = "https://pdf.sciencedirectassets.com/x/main.pdf?a=1&amp;b=2\\u0026c=3";'
    )
    url = rb._signed_asset_url(html)
    assert url == "https://pdf.sciencedirectassets.com/x/main.pdf?a=1&b=2&c=3"


def test_prefs_seeded(tmp_path, monkeypatch):
    prof = tmp_path / "profile"
    monkeypatch.setattr(rb, "profile_dir", lambda: prof)
    monkeypatch.setattr(rb, "windows_path", str)
    rb.set_pdf_download_prefs()
    import json

    data = json.loads((prof / "Default" / "Preferences").read_text())
    assert data["plugins"]["always_open_pdf_externally"] is True
    assert data["download"]["prompt_for_download"] is False
    # scripted multi-download block must not fire in the dedicated profile
    assert data["profile"]["default_content_setting_values"]["automatic_downloads"] == 1
    exceptions = data["profile"]["content_settings"]["exceptions"]["automatic_downloads"]
    assert exceptions["https://www.sciencedirect.com:443,*"]["setting"] == 1


# ── fake Playwright objects ──────────────────────────────────────────────────


class FakePage:
    """goto records urls; evaluate/content are instance-replaceable."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.closed = False
        self.url = ""
        self.gotos: list[str] = []

    async def goto(self, url, **kw):
        self.gotos.append(url)
        handler = self.ctx.goto_handler
        if handler:
            return await handler(self, url)
        self.url = ARTICLE
        return None

    async def wait_for_url(self, *_a, **_k):
        pass

    async def evaluate(self, js, *args):
        return self.ctx.evaluate(self, js, *args)

    async def content(self):
        return self.ctx.content

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self):
        self.pages: list[FakePage] = []
        self.goto_handler = None
        self.content = ""
        self.fire_result = "fired"
        self.pdf_links = [PDFFT]
        self.on_location = None

    def evaluate(self, page, js, *args):
        if "sdUserRedirected" in js:
            return self.fire_result
        if js.startswith("(u)"):
            return self.on_location(page, args[0]) if self.on_location else None
        if "querySelectorAll" in js:
            return self.pdf_links
        return None

    async def new_page(self):
        p = FakePage(self)
        self.pages.append(p)
        return p


class FakeBrowser:
    def __init__(self, ctx):
        self._ctx = ctx
        self.sends: list[tuple] = []

    @property
    def contexts(self):
        return [self._ctx]

    async def new_browser_cdp_session(self):
        me = self

        class Session:
            async def send(self, method, params=None):
                me.sends.append((method, params))

            def on(self, *a, **k):
                pass

        return Session()

    async def close(self):
        pass


def wire_connect(monkeypatch, ctx):
    browser = FakeBrowser(ctx)

    async def fake_connect(_p, _exe):
        return browser, ctx

    monkeypatch.setattr(rb, "connect", fake_connect)
    return browser


# ── download_one ─────────────────────────────────────────────────────────────


class _Later:
    """Fires a background coroutine task once the hop page navigates."""

    def __init__(self, dl: Path, delay: float):
        self.dl = dl
        self.delay = delay
        self.tasks: list[asyncio.Task] = []

    def schedule(self):
        async def fire():
            await asyncio.sleep(self.delay)
            self.write()

        self.tasks.append(asyncio.ensure_future(fire()))

    def write(self, name: str = NAME, body: bytes = PDF_BODY):
        self.dl.mkdir(parents=True, exist_ok=True)
        (self.dl / name).write_bytes(body)


def make_ctx(monkeypatch, tmp_path):
    """A context whose article page is *ARTICLE* and hop page spawns a PDF."""
    ctx = FakeContext()
    dl = tmp_path / "dl"
    monkeypatch.setattr(rb, "download_folder", lambda: dl)
    later: _Later = _Later(dl, 0.0)
    later.delay = 0.3

    async def goto(page, url):
        if "pdfft" in url or ".pdf" in url:
            page.url = ARTICLE  # the interstitial page keeps its pdfft URL
            later.schedule()
        else:
            page.url = ARTICLE

    ctx.goto_handler = goto
    return ctx, dl, later


def test_download_one_files_pdf(monkeypatch, tmp_path):
    ctx, dl, later = make_ctx(monkeypatch, tmp_path)

    async def run():
        item = rb.AutoItem(key=DOI, url=ARTICLE, dest=str(tmp_path / "lib" / "paper.pdf"))
        return await rb.download_one(ctx, item, natural_wait_s=1.0, hop_wait_s=2.0, poll_s=0.05)

    out = asyncio.run(run())
    assert out == str(tmp_path / "lib" / "paper.pdf")
    assert Path(out).read_bytes().startswith(b"%PDF-")
    assert not (dl / NAME).exists()  # the original is consumed


def test_download_one_ignores_unrelated_files(monkeypatch, tmp_path):
    ctx, dl, _ = make_ctx(monkeypatch, tmp_path)

    async def run():
        item = rb.AutoItem(key=DOI, url=ARTICLE, dest=str(tmp_path / "lib" / "p.pdf"))
        return await rb.download_one(ctx, item, natural_wait_s=1.0, hop_wait_s=2.5, poll_s=0.05)

    async def goto(page, url):
        page.url = ARTICLE
        if "pdfft" in url:
            fire = _Later(dl, 0.0)

            async def seq():
                await asyncio.sleep(0.2)
                fire.write("unrelated_thing.pdf", b"not a pdf")
                await asyncio.sleep(0.3)
                fire.write()

            fire.tasks.append(asyncio.ensure_future(seq()))

    ctx.goto_handler = goto
    out = asyncio.run(run())
    assert out == str(tmp_path / "lib" / "p.pdf")


def test_download_one_manual_ignition(monkeypatch, tmp_path):
    ctx = FakeContext()
    dl = tmp_path / "dl"
    dl.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rb, "download_folder", lambda: dl)
    ctx.fire_result = "no-fn"  # natural launcher stalled
    ctx.content = f"stuff {ASSET} more"
    ctx.goto_handler = None

    assigned: dict[str, str] = {}

    def on_location(page, url):
        assigned["url"] = url
        (dl / NAME).write_bytes(PDF_BODY)  # the assignment surfaces as download

    ctx.on_location = on_location

    async def run():
        item = rb.AutoItem(key=DOI, url=ARTICLE, dest=str(tmp_path / "lib" / "p.pdf"))
        return await rb.download_one(ctx, item, natural_wait_s=0.5, hop_wait_s=2.0, poll_s=0.05)

    out = asyncio.run(run())
    assert out == str(tmp_path / "lib" / "p.pdf")
    assert assigned["url"] == ASSET


def _login_ctx(monkeypatch, tmp_path, page_url_fn):
    ctx = FakeContext()
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    async def goto(page, url):
        page.url = page_url_fn(url)

    ctx.goto_handler = goto
    return ctx


def test_download_one_login_required(monkeypatch, tmp_path):
    ctx = _login_ctx(monkeypatch, tmp_path, lambda url: "https://id.elsevier.com/ASX/token")

    async def run():
        item = rb.AutoItem(key="x", url=ARTICLE, dest=str(tmp_path / "a.pdf"))
        return await rb.download_one(ctx, item)

    assert asyncio.run(run()) == "login-required"


def test_download_one_hop_login_wall(monkeypatch, tmp_path):
    """A session that expires mid-run shows the wall on the PDF hop, not the
    article: download_one must still report it as login-required."""
    ctx = _login_ctx(
        monkeypatch,
        tmp_path,
        lambda url: "https://id.elsevier.com/ASX/token" if "/pdfft" in url else ARTICLE,
    )

    async def run():
        item = rb.AutoItem(key=DOI, url=ARTICLE, dest=str(tmp_path / "a.pdf"))
        return await rb.download_one(ctx, item, natural_wait_s=0.3, link_wait_s=0.4)

    assert asyncio.run(run()) == "login-required"


def test_download_one_late_hop_login_wall(monkeypatch, tmp_path):
    """The login redirect can arrive only in the timeout window."""
    ctx = FakeContext()
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")
    (tmp_path / "dl").mkdir(parents=True, exist_ok=True)
    ctx.tasks = []

    async def goto(page, url):
        page.url = ARTICLE
        if "/pdfft" in url:

            async def flip():
                await asyncio.sleep(0.5)
                page.url = "https://id.elsevier.com/ASX/token"

            ctx.tasks.append(asyncio.ensure_future(flip()))

    ctx.goto_handler = goto

    async def run():
        item = rb.AutoItem(key=DOI, url=ARTICLE, dest=str(tmp_path / "a.pdf"))
        return await rb.download_one(
            ctx, item, natural_wait_s=0.3, hop_wait_s=0.9, link_wait_s=0.4, poll_s=0.05
        )

    out = asyncio.run(run())
    for t in ctx.tasks:
        t.cancel()
    assert out == "login-required"


def test_download_one_no_pdf_link(monkeypatch, tmp_path):
    ctx, _, _ = make_ctx(monkeypatch, tmp_path)
    ctx.pdf_links = []

    async def run():
        item = rb.AutoItem(key=DOI, url=ARTICLE, dest=str(tmp_path / "a.pdf"))
        return await rb.download_one(ctx, item, natural_wait_s=0.3, link_wait_s=0.5)

    # The fake context has no page content: a thrown-away shell reads as a
    # challenge page, which is what Elsevier's bot check serves in this spot.
    assert asyncio.run(run()) == "challenge"


def test_download_one_challenge_reported_as_human_check(monkeypatch, tmp_path):
    """A redirected article page that never offers a PDF is named, not bare 'no PDF'."""
    ctx = FakeContext()
    ctx.pdf_links = []
    wire_connect(monkeypatch, ctx)
    monkeypatch.setattr(rb, "find_chrome", lambda: Path("/usr/bin/chrome"))
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    real = rb.download_one

    async def fake_one(_ctx, item, **kw):
        return await real(_ctx, item, natural_wait_s=0.2, link_wait_s=0.4)

    monkeypatch.setattr(rb, "download_one", fake_one)
    notes: dict[str, str] = {}

    async def run():
        item = rb.AutoItem(key="a", url=ARTICLE, dest=str(tmp_path / "a.pdf"))
        return await rb.auto_download([item], on_result=lambda k, p, n: notes.setdefault(k, n))

    asyncio.run(run())
    assert notes["a"] == "no PDF: the page asked for a human check"


def test_download_one_hop_403_is_a_login_wall(monkeypatch, tmp_path):
    """An Atypon site (AIAA) answers an unentitled PDF with a 403 page: that is
    a login wall at once, not an 83-second wait for a download that never comes."""
    ctx = FakeContext()
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")
    ctx.content = "<html>" + "Access denied. " * 400 + "</html>"
    aiaa = "https://arc.aiaa.org/doi/10.2514/1.C037192"
    ctx.pdf_links = ["https://arc.aiaa.org/doi/pdf/10.2514/1.C037192?download=true"]

    async def goto(page, url):
        page.url = url if "/doi/pdf/" in url else aiaa
        return types.SimpleNamespace(status=403 if "/doi/pdf/" in url else 200)

    ctx.goto_handler = goto

    async def run():
        item = rb.AutoItem(key="10.2514/1.c037192", url=aiaa, dest=str(tmp_path / "a.pdf"))
        return await rb.download_one(ctx, item, natural_wait_s=30, hop_wait_s=30)

    assert asyncio.run(asyncio.wait_for(run(), timeout=5)) == "login-required"


def test_download_one_waits_for_a_human_check(monkeypatch, tmp_path):
    """In an attended run a check page is handed to the user, then the paper goes on."""
    ctx, _dl, _later = make_ctx(monkeypatch, tmp_path)
    ctx.pdf_links = []  # the Cloudflare shell: no links, short body
    monkeypatch.setattr(rb.sys.stdin, "isatty", lambda: True)
    asked: list[bool] = []

    def on_check():
        asked.append(True)
        ctx.pdf_links = [PDFFT]  # the user clicked the box: the article renders

    async def run():
        item = rb.AutoItem(key=DOI, url=ARTICLE, dest=str(tmp_path / "lib" / "p.pdf"))
        return await rb.download_one(
            ctx,
            item,
            link_wait_s=0.2,
            check_wait_s=5,
            natural_wait_s=2,
            poll_s=0.05,
            on_check=on_check,
        )

    assert asyncio.run(run()) == str(tmp_path / "lib" / "p.pdf")
    assert asked == [True]


class _PipeStdin:
    """A TTY-looking stdin backed by a pipe, so the event loop can watch it."""

    def __init__(self, text: str):
        import os

        r, w = os.pipe()
        os.write(w, text.encode())
        os.close(w)
        self._f = os.fdopen(r, "r")

    def fileno(self):
        return self._f.fileno()

    def readline(self):
        return self._f.readline()

    def isatty(self):
        return True


@pytest.mark.parametrize(("typed", "cmd"), [("\n", "next"), ("s\n", "skip"), ("q\n", "quit")])
def test_wait_for_enter_reads_and_consumes_the_line(monkeypatch, typed, cmd):
    """The pressed line is read, so it cannot leak into the next paper's wait."""
    stdin = _PipeStdin(typed + "left over\n")
    monkeypatch.setattr(rb.sys, "stdin", stdin)

    assert asyncio.run(rb.wait_for_enter()) == cmd
    assert stdin.readline() == "left over\n"


def test_download_one_times_out(monkeypatch, tmp_path):
    ctx = FakeContext()
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")
    (tmp_path / "dl").mkdir()

    async def goto(page, url):
        page.url = ARTICLE

    ctx.goto_handler = goto

    async def run():
        item = rb.AutoItem(key=DOI, url=ARTICLE, dest=str(tmp_path / "a.pdf"))
        return await rb.download_one(ctx, item, natural_wait_s=0.3, hop_wait_s=0.4, poll_s=0.05)

    assert asyncio.run(run()) is None


# ── auto_download orchestration ──────────────────────────────────────────────


def test_auto_download_success_and_results(monkeypatch, tmp_path):
    ctx = FakeContext()
    browser = wire_connect(monkeypatch, ctx)
    monkeypatch.setattr(rb, "find_chrome", lambda: Path("/usr/bin/chrome"))
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    async def fake_one(_ctx, item, **kw):
        return f"/lib/{item.key}.pdf"

    monkeypatch.setattr(rb, "download_one", fake_one)
    notes: dict[str, tuple] = {}

    def on_result(key, path, note):
        notes[key] = (path, note)

    async def run():
        items = [rb.AutoItem(key="a", url="u1", dest="x"), rb.AutoItem(key="b", url="u2", dest="y")]
        return await rb.auto_download(items, on_result=on_result, politeness_s=(0, 0))

    saved = asyncio.run(run())
    assert saved == {"a": "/lib/a.pdf", "b": "/lib/b.pdf"}
    assert notes["a"] == ("/lib/a.pdf", "")
    assert notes["b"] == ("/lib/b.pdf", "")
    assert [s[:1] for s in browser.sends] == [("Browser.setDownloadBehavior",)]


def test_auto_download_aborts_after_repeated_walls(monkeypatch, tmp_path):
    ctx = FakeContext()
    wire_connect(monkeypatch, ctx)
    monkeypatch.setattr(rb, "find_chrome", lambda: Path("/usr/bin/chrome"))
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    async def fake_one(_ctx, item, **kw):
        return None  # a wall every time

    monkeypatch.setattr(rb, "download_one", fake_one)
    notes: list[tuple[str, str]] = []

    def on_result(key, path, note):
        notes.append((key, note))

    async def run():
        items = [rb.AutoItem(key=k, url="u", dest="d") for k in "abcde"]
        return await rb.auto_download(
            items, on_result=on_result, politeness_s=(0, 0), block_abort_after=2
        )

    asyncio.run(run())
    keys = [k for k, _ in notes]
    assert keys == ["a", "b", "c", "d", "e"]
    assert notes[0] == ("a", "no PDF arrived")
    assert notes[1] == ("b", "no PDF arrived")
    assert notes[2] == ("c", "stopped: repeated walls")
    assert notes[3] == ("d", "stopped: repeated walls")
    assert notes[4] == ("e", "stopped: repeated walls")


def test_auto_download_one_site_stops_the_others(monkeypatch, tmp_path):
    """Site A aborts after its walls; site B's papers still download after it.

    This is the bibliographic case that ate a whole run before the grouping:
    dozens of ScienceDirect papers starved behind another site's walls.
    """
    ctx = FakeContext()
    wire_connect(monkeypatch, ctx)
    monkeypatch.setattr(rb, "find_chrome", lambda: Path("/usr/bin/chrome"))
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    async def fake_one(_ctx, item, **kw):
        return None if "site-a" in item.url else f"/lib/{item.key}.pdf"

    monkeypatch.setattr(rb, "download_one", fake_one)
    notes: dict[str, str] = {}

    def on_result(key, path, note):
        notes[key] = note

    async def run():
        items = [
            rb.AutoItem(key="a", url="https://site-a.test/a", dest="d"),
            rb.AutoItem(key="b", url="https://site-a.test/b", dest="d"),
            rb.AutoItem(key="c", url="https://site-a.test/c", dest="d"),
            rb.AutoItem(key="d", url="https://elsevier-test.test/w", dest="d"),
            rb.AutoItem(key="e", url="https://elsevier-test.test/v", dest="d"),
        ]
        return await rb.auto_download(
            items, on_result=on_result, politeness_s=(0, 0), block_abort_after=2
        )

    saved = asyncio.run(run())
    assert set(saved) == {"d", "e"}  # site B flows after site A aborts
    assert notes["a"] == "no PDF arrived"
    assert notes["c"] == "stopped: repeated walls"


def test_auto_download_needs_no_press_between_papers(monkeypatch, tmp_path):
    """The pass runs by itself, even in a terminal: nobody presses anything."""
    ctx = FakeContext()
    browser = wire_connect(monkeypatch, ctx)
    monkeypatch.setattr(rb, "find_chrome", lambda: Path("/usr/bin/chrome"))
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    async def fake_one(_ctx, item, **kw):
        return f"/lib/{item.key}.pdf"

    monkeypatch.setattr(rb, "download_one", fake_one)

    async def never_pressed(cb=None):
        await asyncio.sleep(3600)

    monkeypatch.setattr(rb, "wait_for_enter", never_pressed)
    monkeypatch.setattr(rb.sys.stdin, "isatty", lambda: True)

    async def run():
        items = [rb.AutoItem(key=k, url="u", dest="d") for k in "abc"]
        return await rb.auto_download([*items], politeness_s=(0, 0))

    saved = asyncio.run(asyncio.wait_for(run(), timeout=5))
    assert saved == {"a": "/lib/a.pdf", "b": "/lib/b.pdf", "c": "/lib/c.pdf"}
    assert len(browser.sends) == 1  # download behavior still claimed once


def test_auto_download_quit_during_a_flight_ends_the_run(monkeypatch, tmp_path):
    """`q` while a paper is in flight stops it and reports the rest as hand-stopped."""
    ctx = FakeContext()
    wire_connect(monkeypatch, ctx)
    monkeypatch.setattr(rb, "find_chrome", lambda: Path("/usr/bin/chrome"))
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    driven: list[str] = []

    async def slow_one(_ctx, item, **kw):
        driven.append(item.key)
        await asyncio.sleep(3600)

    monkeypatch.setattr(rb, "download_one", slow_one)

    async def fake_wait(cb=None):
        return "quit"

    monkeypatch.setattr(rb, "wait_for_enter", fake_wait)
    monkeypatch.setattr(rb.sys.stdin, "isatty", lambda: True)
    notes: dict[str, str] = {}

    async def run():
        items = [rb.AutoItem(key=k, url="u", dest="d") for k in "abc"]
        return await rb.auto_download(
            [*items], on_result=lambda k, _p, n: notes.setdefault(k, n), politeness_s=(0, 0)
        )

    assert asyncio.run(run()) == {}
    assert driven == ["a"]
    assert notes == dict.fromkeys("abc", "stopped: by hand (Enter)")


def test_auto_download_enter_during_a_flight_skips_it(monkeypatch, tmp_path):
    """A press while the current paper is in flight abandons that paper."""
    ctx = FakeContext()
    wire_connect(monkeypatch, ctx)
    monkeypatch.setattr(rb, "find_chrome", lambda: Path("/usr/bin/chrome"))
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    driven: list[str] = []

    async def slow_one(_ctx, item, **kw):
        driven.append(item.key)
        await asyncio.sleep(3600)  # the stuck crawl the user wants out of

    monkeypatch.setattr(rb, "download_one", slow_one)

    async def fake_wait(cb=None):
        return "next"

    monkeypatch.setattr(rb, "wait_for_enter", fake_wait)
    monkeypatch.setattr(rb.sys.stdin, "isatty", lambda: True)
    notes: dict[str, str] = {}

    async def run():
        items = [rb.AutoItem(key=k, url="u", dest="d") for k in "ab"]
        return await rb.auto_download([*items], on_result=lambda k, _p, n: notes.setdefault(k, n))

    asyncio.run(run())
    assert driven == ["a", "b"]
    assert notes["a"] == "skipped: by hand (Enter)"


def test_auto_download_skips_login_walls_and_goes_on(monkeypatch, tmp_path):
    """A site the profile has no access to is skipped, never waited on: after 3
    login walls in a row its other papers are not even opened, and the sites
    with access still download."""
    ctx = FakeContext()
    wire_connect(monkeypatch, ctx)
    monkeypatch.setattr(rb, "find_chrome", lambda: Path("/usr/bin/chrome"))
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    driven: list[str] = []

    async def fake_one(_ctx, item, **kw):
        driven.append(item.key)
        if "aiaa" in item.url:
            return "login-required"
        return f"/lib/{item.key}.pdf"

    monkeypatch.setattr(rb, "download_one", fake_one)
    notes: dict[str, str] = {}

    async def run():
        items = [
            *(
                rb.AutoItem(key=f"a{i}", url=f"https://arc.aiaa.org/{i}", dest="d")
                for i in range(5)
            ),
            rb.AutoItem(key="sd", url="https://www.sciencedirect.com/x", dest="d"),
        ]
        return await rb.auto_download(
            items, on_result=lambda k, _p, n: notes.setdefault(k, n), politeness_s=(0, 0)
        )

    saved = asyncio.run(asyncio.wait_for(run(), timeout=5))
    assert saved == {"sd": "/lib/sd.pdf"}
    assert driven == ["a0", "a1", "a2", "sd"]
    assert notes["a0"] == "login required: arc.aiaa.org"
    assert notes["a3"] == notes["a4"] == "skipped: arc.aiaa.org asks for a login"


def test_auto_download_no_chrome_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(rb, "find_chrome", lambda: None)
    monkeypatch.setattr(rb, "_port_open", lambda *a, **k: False)

    async def run():
        items = [rb.AutoItem(key="a", url="https://doi.org/10.a/b", dest="d")]
        return await rb.auto_download(items)

    with pytest.raises(DependencyError):
        asyncio.run(run())


def test_auto_download_without_playwright_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.async_api", None)  # import -> ImportError

    async def run():
        return await rb.auto_download([rb.AutoItem(key="a", url="u", dest="d")])

    with pytest.raises(DependencyError, match=r"mosaic-search\[browser\]"):
        asyncio.run(run())


@pytest.fixture(autouse=True)
def _no_resolve(monkeypatch):
    """No network in tests: the site grouping uses the URL as given."""
    monkeypatch.setattr(rb, "resolve_landing", lambda u: u)


def test_auto_download_reports_deferred(monkeypatch, tmp_path):
    ctx = FakeContext()
    wire_connect(monkeypatch, ctx)
    monkeypatch.setattr(rb, "find_chrome", lambda: Path("/usr/bin/chrome"))
    monkeypatch.setattr(rb, "download_folder", lambda: tmp_path / "dl")

    async def fake_one(_ctx, item, **kw):
        return f"/lib/{item.key}"

    monkeypatch.setattr(rb, "download_one", fake_one)
    deferred_notes: list[tuple[str, str]] = []

    def on_result(key, path, note):
        if note.startswith("skipped"):
            deferred_notes.append((key, note))

    async def run():
        items = [rb.AutoItem(key=f"k{i}", url="u", dest="d") for i in range(4)]
        return await rb.auto_download(items, on_result=on_result, politeness_s=(0, 0), max_papers=2)

    saved = asyncio.run(run())
    assert set(saved) == {"k0", "k1"}
    assert deferred_notes == [
        ("k2", "skipped: over the per-run cap"),
        ("k3", "skipped: over the per-run cap"),
    ]


# ── sync entry ───────────────────────────────────────────────────────────────


def test_auto_download_sync_tuple_accuracy(monkeypatch):
    seen: dict = {}

    async def fake_auto(items, **kw):
        seen["keys"] = [i.key for i in items]
        seen["urls"] = [i.url for i in items]
        seen["dests"] = [i.dest for i in items]
        return {i.key: "/p" for i in items}

    monkeypatch.setattr(rb, "auto_download", fake_auto)
    saved, state = rb.auto_download_sync([("k", "label", "u", "d")])
    assert (saved, state) == ({"k": "/p"}, "")
    assert seen["keys"] == ["k"] and seen["urls"] == ["u"] and seen["dests"] == ["d"]


def test_auto_download_sync_dependency_state(monkeypatch):
    def boom(items, **kw):
        raise DependencyError("no chrome")

    monkeypatch.setattr(rb, "auto_download", boom)
    saved, state = rb.auto_download_sync([("k", "l", "u", "d")])
    assert (saved, state) == ({}, "dependency")


def test_auto_download_sync_crash_state(monkeypatch):
    def boom(items, **kw):
        raise RuntimeError("x")

    monkeypatch.setattr(rb, "auto_download", boom)
    saved, state = rb.auto_download_sync([("k", "l", "u", "d")])
    assert (saved, state) == ({}, "failed")


def test_auto_download_sync_empty_ok():
    async def fake(items, **kw):
        return {}

    with patch.object(rb, "auto_download", fake):
        saved, state = rb.auto_download_sync([("k", "l", "u", "d")])
    assert state == "failed"
