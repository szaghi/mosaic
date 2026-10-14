"""Tests for handing downloads to the user's own browser (``get --handoff``)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

from mosaic import handoff
from mosaic.handoff import DownloadWatcher, handoff_download

PDF = b"%PDF-1.7\n" + b"x" * 2000


def _poll_until(watcher: DownloadWatcher, n: int = 5) -> Path | None:
    for _ in range(n):
        found = watcher.poll()
        if found:
            return found
    return None


class TestDownloadWatcher:
    def test_files_present_before_arm_are_ignored(self, tmp_path):
        (tmp_path / "old.pdf").write_bytes(PDF)
        w = DownloadWatcher(tmp_path)
        w.arm()
        assert _poll_until(w) is None

    def test_new_pdf_needs_a_stable_size_across_two_polls(self, tmp_path):
        w = DownloadWatcher(tmp_path)
        w.arm()
        (tmp_path / "paper.pdf").write_bytes(PDF)
        assert w.poll() is None  # first sighting: could still be growing
        assert w.poll() == tmp_path / "paper.pdf"

    def test_chrome_partial_file_is_ignored_until_renamed(self, tmp_path):
        w = DownloadWatcher(tmp_path)
        w.arm()
        part = tmp_path / "1-s2.0-S0094576517312663-main.pdf.crdownload"
        part.write_bytes(PDF[:500])
        assert _poll_until(w) is None
        part.rename(tmp_path / "1-s2.0-S0094576517312663-main.pdf")
        assert _poll_until(w) == tmp_path / "1-s2.0-S0094576517312663-main.pdf"

    def test_final_name_ignored_while_partial_companion_exists(self, tmp_path):
        """Firefox creates the final name empty and writes into name.part."""
        w = DownloadWatcher(tmp_path)
        w.arm()
        (tmp_path / "paper.pdf").write_bytes(PDF)
        (tmp_path / "paper.pdf.part").write_bytes(b"...")
        assert _poll_until(w) is None

    def test_non_pdf_download_is_ignored(self, tmp_path):
        w = DownloadWatcher(tmp_path)
        w.arm()
        (tmp_path / "access-denied.pdf").write_bytes(b"<html>403</html>")
        assert _poll_until(w) is None

    def test_overwritten_existing_file_counts_as_new(self, tmp_path):
        f = tmp_path / "paper.pdf"
        f.write_bytes(b"<html>old</html>")
        w = DownloadWatcher(tmp_path)
        w.arm()
        time.sleep(0.01)
        f.write_bytes(PDF)
        assert _poll_until(w) == f


class TestHandoffDownload:
    def _browser_that_downloads(self, folder: Path, name: str, body: bytes, delay: float = 0.05):
        opened = []

        def opener(url: str) -> bool:
            opened.append(url)

            def write():
                time.sleep(delay)
                (folder / f"{name}.crdownload").write_bytes(body[:100])
                time.sleep(delay)
                (folder / f"{name}.crdownload").write_bytes(body)
                (folder / f"{name}.crdownload").rename(folder / name)

            threading.Thread(target=write, daemon=True).start()
            return True

        return opener, opened

    def test_pdf_downloaded_by_user_is_moved_to_dest(self, tmp_path):
        downloads, library = tmp_path / "Downloads", tmp_path / "papers"
        downloads.mkdir()
        opener, opened = self._browser_that_downloads(downloads, "1-s2.0-S009-main.pdf", PDF)
        results = []
        out = handoff_download(
            [
                (
                    "10.1016/x",
                    "Paper X (2018)",
                    "https://www.sciencedirect.com/pii/S009",
                    str(library / "x.pdf"),
                )
            ],
            downloads,
            wait_s=5,
            poll_s=0.02,
            opener=opener,
            on_result=lambda *a: results.append(a),
        )
        assert opened == ["https://www.sciencedirect.com/pii/S009"]
        assert out == {"10.1016/x": str(library / "x.pdf")}
        assert (library / "x.pdf").read_bytes() == PDF
        assert not (downloads / "1-s2.0-S009-main.pdf").exists()  # moved, not copied
        assert results == [("10.1016/x", str(library / "x.pdf"), "1-s2.0-S009-main.pdf")]

    def test_nothing_downloaded_times_out_and_reports_skip(self, tmp_path):
        results = []
        out = handoff_download(
            [("k", "label", "https://x", str(tmp_path / "x.pdf"))],
            tmp_path,
            wait_s=0.1,
            poll_s=0.02,
            opener=lambda u: True,
            on_result=lambda *a: results.append(a),
        )
        assert out == {}
        assert results == [("k", None, None)]

    def test_each_paper_only_takes_pdfs_arriving_after_it_was_opened(self, tmp_path):
        """One paper at a time: a PDF from paper 1 must not be filed as paper 2."""
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        opener1, _ = self._browser_that_downloads(downloads, "first.pdf", PDF)
        calls = {"n": 0}

        def opener(url):
            calls["n"] += 1
            return opener1(url) if calls["n"] == 1 else True

        out = handoff_download(
            [
                ("a", "A", "https://a", str(tmp_path / "a.pdf")),
                ("b", "B", "https://b", str(tmp_path / "b.pdf")),
            ],
            downloads,
            wait_s=2,
            poll_s=0.02,
            opener=opener,
        )
        assert set(out) == {"a"}


class TestEnvironment:
    def test_wsl_downloads_dir_asks_windows_for_known_folder(self, tmp_path):
        target = tmp_path / "Downloads"
        target.mkdir()
        answers = {"powershell.exe": r"C:\Users\me\OneDrive\Downloads", "wslpath": str(target)}
        with (
            patch.object(handoff, "is_wsl", return_value=True),
            patch.object(handoff, "_run", side_effect=lambda cmd, **k: answers[cmd[0]]),
        ):
            assert handoff.default_downloads_dir() == target

    def test_wsl_opens_url_with_windows_browser(self):
        with (
            patch.object(handoff, "is_wsl", return_value=True),
            patch(
                "mosaic.handoff.shutil.which",
                side_effect=lambda c: c if c == "explorer.exe" else None,
            ),
            patch("mosaic.handoff.subprocess.Popen") as popen,
        ):
            assert handoff.open_in_browser("https://doi.org/10.1/x?a=1&b=2") is True
        # Passed as an argument vector: no shell, so '&' in URLs is safe.
        assert popen.call_args.args[0] == ["explorer.exe", "https://doi.org/10.1/x?a=1&b=2"]


class TestGetHandoffCli:
    def test_failed_papers_handed_off_and_counted(self, tmp_path, tmp_cache):
        from typer.testing import CliRunner

        from mosaic.cli import app
        from mosaic.models import Paper

        csv = tmp_path / "dois.csv"
        csv.write_text("doi\n10.1016/a\n10.1016/b\n")
        cfg = {
            "db_path": ":memory:",
            "download_dir": str(tmp_path / "dl"),
            "unpaywall": {"email": ""},
        }

        def fake_handoff(items, folder, on_result=None, announce=None, **kw):
            key, _label, url, dest = items[0]
            assert url == "https://landing/10.1016/a"
            if on_result:
                on_result(key, dest, "main.pdf")
            return {key: dest}

        with (
            patch("mosaic.cli.cfg_mod.load", return_value=cfg),
            patch("mosaic.cli.Cache", return_value=tmp_cache),
            patch(
                "mosaic.cite.paper_for_download",
                side_effect=lambda d, *a: Paper(title=f"T {d}", doi=d, year=2018),
            ),
            patch("mosaic.cli.dl_paper", return_value=None),
            patch(
                "mosaic.downloader.resolve_landing",
                side_effect=lambda u: "https://landing/" + u.split("doi.org/")[-1],
            ),
            patch("mosaic.handoff.handoff_download", side_effect=fake_handoff) as ho,
        ):
            r = CliRunner().invoke(
                app, ["get", "--from", str(csv), "--handoff", "--watch-dir", str(tmp_path)]
            )
        assert r.exit_code == 0, r.output
        ho.assert_called_once()
        assert "1 downloaded" in r.output and "1 failed" in r.output
        assert tmp_cache.get_download(Paper(title="x", doi="10.1016/a").uid)["status"] == "ok"

    def test_missing_watch_dir_is_reported(self, tmp_path, tmp_cache):
        from typer.testing import CliRunner

        from mosaic.cli import app
        from mosaic.models import Paper

        cfg = {
            "db_path": ":memory:",
            "download_dir": str(tmp_path / "dl"),
            "unpaywall": {"email": ""},
        }
        with (
            patch("mosaic.cli.cfg_mod.load", return_value=cfg),
            patch("mosaic.cli.Cache", return_value=tmp_cache),
            patch(
                "mosaic.cite.paper_for_download", side_effect=lambda d, *a: Paper(title="T", doi=d)
            ),
            patch("mosaic.cli.dl_paper", return_value=None),
            patch("mosaic.handoff.default_downloads_dir", return_value=None),
        ):
            r = CliRunner().invoke(app, ["get", "10.1016/a", "--handoff"])
        assert "--watch-dir" in r.output


class TestCollect:
    def test_locked_original_is_retried_then_left_in_place(self, tmp_path):
        """WSL: Windows briefly locks a fresh download; filing must not crash."""
        from mosaic.handoff import _collect

        src = tmp_path / "Downloads" / "main.pdf"
        src.parent.mkdir()
        src.write_bytes(PDF)
        dest = tmp_path / "lib" / "x.pdf"
        with patch.object(Path, "unlink", side_effect=PermissionError("locked")):
            removed = _collect(src, str(dest), unlink_wait_s=0.6)
        assert removed is False
        assert dest.read_bytes() == PDF
        assert src.exists()
        assert not dest.with_name("x.pdf.part").exists()

    def test_lock_released_during_retry(self, tmp_path):
        from mosaic.handoff import _collect

        src = tmp_path / "main.pdf"
        src.write_bytes(PDF)
        real_unlink = Path.unlink
        calls = {"n": 0}

        def flaky(self, *a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError("locked")
            return real_unlink(self, *a, **k)

        with patch.object(Path, "unlink", flaky):
            assert _collect(src, str(tmp_path / "lib" / "x.pdf"), unlink_wait_s=3) is True
        assert not src.exists()


class TestEnterMeansDone:
    """Users press Enter right after clicking Download: that must not discard the file."""

    def test_pdf_finishing_after_enter_is_still_filed(self, tmp_path):
        from mosaic import handoff as ho

        downloads = tmp_path / "Downloads"
        downloads.mkdir()

        def opener(url):
            def write():
                time.sleep(0.15)  # lands after the user's Enter
                (downloads / "main.pdf").write_bytes(PDF)

            threading.Thread(target=write, daemon=True).start()
            return True

        presses = iter([True])  # Enter on the first poll
        with patch.object(
            ho, "_enter_pressed", side_effect=lambda t: next(presses, False) or time.sleep(t)
        ):
            out = handoff_download(
                [("k", "L", "https://x", str(tmp_path / "x.pdf"))],
                downloads,
                wait_s=10,
                poll_s=0.05,
                grace_s=1.0,
                opener=opener,
            )
        assert out == {"k": str(tmp_path / "x.pdf")}

    def test_enter_with_no_download_skips_after_grace(self, tmp_path):
        from mosaic import handoff as ho

        with patch.object(ho, "_enter_pressed", return_value=True):
            t0 = time.monotonic()
            out = handoff_download(
                [("k", "L", "https://x", str(tmp_path / "x.pdf"))],
                tmp_path,
                wait_s=10,
                poll_s=0.05,
                grace_s=0.3,
                opener=lambda u: True,
            )
        assert out == {}
        assert time.monotonic() - t0 < 2  # skipped promptly, not after wait_s

    def test_grace_extended_while_browser_is_still_writing(self, tmp_path):
        from mosaic import handoff as ho

        def opener(url):
            def write():
                (tmp_path / "big.pdf.crdownload").write_bytes(PDF[:10])
                time.sleep(0.8)  # longer than grace_s
                (tmp_path / "big.pdf.crdownload").write_bytes(PDF)
                (tmp_path / "big.pdf.crdownload").rename(tmp_path / "big.pdf")

            threading.Thread(target=write, daemon=True).start()
            return True

        presses = iter([False, True])
        with patch.object(
            ho, "_enter_pressed", side_effect=lambda t: next(presses, False) or time.sleep(t)
        ):
            out = handoff_download(
                [("k", "L", "https://x", str(tmp_path / "lib" / "x.pdf"))],
                tmp_path,
                wait_s=10,
                poll_s=0.05,
                grace_s=0.2,
                opener=opener,
            )
        assert out == {"k": str(tmp_path / "lib" / "x.pdf")}
