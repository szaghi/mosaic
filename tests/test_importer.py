"""Tests for ``mosaic import`` (filing user-downloaded PDFs)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mosaic.importer import PdfImportError, detect_doi, import_pdf
from mosaic.models import Paper


def _pdf(path: Path, body: bytes = b"") -> Path:
    path.write_bytes(b"%PDF-1.5\n" + body)
    return path


class TestDetectDoi:
    def test_own_doi_in_metadata_wins_over_cited_dois(self, tmp_path):
        f = _pdf(
            tmp_path / "x.pdf",
            b"<prism:doi>10.1016/j.paerosci.2006.01.001</prism:doi> refs: 10.1063/1.1 10.1088/2",
        )
        assert detect_doi(f) == ("10.1016/j.paerosci.2006.01.001", "metadata")

    def test_metadata_near_end_of_large_file_is_found(self, tmp_path):
        """Elsevier writes XMP near the end (3.08 MB into a 3.35 MB file)."""
        from mosaic import importer

        filler = b"x" * (importer._SCAN_BYTES + 1_000_000)
        f = _pdf(
            tmp_path / "Title-words_2018_Acta-Astronau.pdf",
            filler + b"<prism:doi>10.1016/j.actaastro.2017.12.041</prism:doi>",
        )
        assert detect_doi(f) == ("10.1016/j.actaastro.2017.12.041", "metadata")

    def test_doi_straddling_a_chunk_boundary_is_found(self, tmp_path, monkeypatch):
        from mosaic import importer

        monkeypatch.setattr(importer, "_CHUNK", 64)
        field = b"<prism:doi>10.1016/j.actaastro.2017.12.041</prism:doi>"
        f = tmp_path / "x.pdf"
        f.write_bytes(
            b"%PDF-1.5\n" + b"y" * (64 - 9 - 10) + field
        )  # field starts 10 bytes before the boundary
        assert detect_doi(f) == ("10.1016/j.actaastro.2017.12.041", "metadata")

    def test_info_dict_doi_with_closing_paren(self, tmp_path):
        """Elsevier writes /doi (10.1016/...) in the Info dictionary."""
        f = _pdf(tmp_path / "x.pdf", b"/doi (10.1016/j.paerosci.2006.01.001)")
        assert detect_doi(f) == ("10.1016/j.paerosci.2006.01.001", "metadata")

    def test_elsevier_filename_pii_resolved_via_crossref(self, tmp_path):
        f = _pdf(tmp_path / "1-s2.0-S0376042106000029-main.pdf")
        with patch(
            "mosaic.importer.doi_from_pii", return_value="10.1016/j.paerosci.2006.01.001"
        ) as look:
            assert detect_doi(f) == ("10.1016/j.paerosci.2006.01.001", "filename")
        assert look.call_args.args[0] == "S0376042106000029"

    def test_single_doi_in_content_is_used(self, tmp_path):
        f = _pdf(tmp_path / "x.pdf", b"see https://doi.org/10.3390/aerospace8060148.")
        assert detect_doi(f) == ("10.3390/aerospace8060148", "content")

    def test_several_dois_in_content_are_ambiguous(self, tmp_path):
        f = _pdf(tmp_path / "x.pdf", b"10.1063/1.4864625 and 10.1063/1.4972269")
        assert detect_doi(f) is None


@pytest.fixture
def cfg(tmp_path):
    return {"download_dir": str(tmp_path / "library"), "unpaywall": {"email": ""}}


def _meta(doi, *a):
    return Paper(
        title="Numerical modeling of thrusters",
        doi=doi,
        year=2005,
        authors=["Mikellides I"],
        source="Crossref",
    )


class TestImportPdf:
    def test_moved_renamed_and_recorded(self, tmp_path, tmp_cache, cfg):
        src = _pdf(
            tmp_path / "1-s2.0-S0376042106000029-main.pdf", b"/doi (10.1016/j.paerosci.2006.01.001)"
        )
        with patch("mosaic.importer.paper_for_download", side_effect=_meta):
            res = import_pdf(src, tmp_cache, cfg)
        assert res.dest.parent == tmp_path / "library"
        assert res.dest.name.startswith("2005_Crossref_")
        assert res.dest.read_bytes().startswith(b"%PDF-")
        assert not src.exists() and res.original_removed
        rec = tmp_cache.get_download(res.paper.uid)
        assert (rec["status"], rec["local_path"]) == ("ok", str(res.dest))

    def test_given_doi_accepts_doi_prefix_and_skips_detection(self, tmp_path, tmp_cache, cfg):
        src = _pdf(tmp_path / "anything.pdf")
        with (
            patch("mosaic.importer.paper_for_download", side_effect=_meta) as meta,
            patch("mosaic.importer.detect_doi") as detect,
        ):
            res = import_pdf(src, tmp_cache, cfg, doi="doi:10.1016/J.X")
        detect.assert_not_called()
        assert meta.call_args.args[0] == "10.1016/J.X"
        assert res.doi_source == "given"

    def test_non_pdf_rejected_and_left_alone(self, tmp_path, tmp_cache, cfg):
        src = tmp_path / "x.pdf"
        src.write_bytes(b"<html>Access denied</html>")
        with pytest.raises(PdfImportError, match="not a PDF"):
            import_pdf(src, tmp_cache, cfg)
        assert src.exists()

    def test_undetectable_doi_asks_for_it(self, tmp_path, tmp_cache, cfg):
        src = _pdf(tmp_path / "scan.pdf")
        with pytest.raises(PdfImportError, match="--doi"):
            import_pdf(src, tmp_cache, cfg)

    def test_existing_pdf_not_overwritten_without_force(self, tmp_path, tmp_cache, cfg):
        with patch("mosaic.importer.paper_for_download", side_effect=_meta):
            first = import_pdf(_pdf(tmp_path / "a.pdf"), tmp_cache, cfg, doi="10.1/x")
            second = _pdf(tmp_path / "b.pdf", b"newer")
            with pytest.raises(PdfImportError, match="--force"):
                import_pdf(second, tmp_cache, cfg, doi="10.1/x")
            assert second.exists()
            import_pdf(second, tmp_cache, cfg, doi="10.1/x", force=True)
        assert first.dest.read_bytes().endswith(b"newer")

    def test_html_left_by_old_versions_is_replaced(self, tmp_path, tmp_cache, cfg):
        with patch("mosaic.importer.paper_for_download", side_effect=_meta):
            dest = Path(cfg["download_dir"]) / _meta("10.1/x").safe_filename(
                "{year}_{source}_{author}_{title}"
            )
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b"<html>Client Challenge</html>")
            res = import_pdf(_pdf(tmp_path / "a.pdf"), tmp_cache, cfg, doi="10.1/x")
        assert res.dest == dest and dest.read_bytes().startswith(b"%PDF-")


class TestImportCli:
    def test_reports_each_file_and_exits_nonzero_on_failure(self, tmp_path, tmp_cache):
        from typer.testing import CliRunner

        from mosaic.cli import app

        good = _pdf(tmp_path / "good.pdf", b"/doi (10.1016/j.paerosci.2006.01.001)")
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        cfg = {
            "db_path": ":memory:",
            "download_dir": str(tmp_path / "lib"),
            "unpaywall": {"email": ""},
        }
        with (
            patch("mosaic.cli.cfg_mod.load", return_value=cfg),
            patch("mosaic.cli.Cache", return_value=tmp_cache),
            patch("mosaic.importer.paper_for_download", side_effect=_meta),
        ):
            r = CliRunner().invoke(app, ["import", str(good), str(bad)])
        assert r.exit_code == 1
        # Rich wraps at 80 columns, and where depends on the tmp path length
        # (it differs on CI), so compare whitespace-normalised output.
        out = " ".join(r.output.split())
        assert "good.pdf →" in out and "found via metadata" in out
        assert "not a PDF" in out

    def test_doi_with_several_files_rejected(self, tmp_path):
        from typer.testing import CliRunner

        from mosaic.cli import app

        r = CliRunner().invoke(app, ["import", "a.pdf", "b.pdf", "--doi", "10.1/x"])
        assert r.exit_code == 1 and "single file" in r.output
