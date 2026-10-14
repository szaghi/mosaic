"""Tests for mosaic/pdf.py -- PDF text extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestIsAvailable:
    def test_returns_true_when_fitz_importable(self):
        from mosaic.pdf import is_available

        mock_fitz = MagicMock()
        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            assert is_available() is True

    def test_returns_false_when_fitz_missing(self):
        from mosaic.pdf import is_available

        with patch.dict("sys.modules", {"fitz": None}):
            assert is_available() is False


class TestExtractText:
    def _make_mock_doc(self, pages: list[str], encrypted: bool = False) -> MagicMock:
        def mock_page(text: str) -> MagicMock:
            return MagicMock(**{"get_text.return_value": text})

        doc = MagicMock()
        doc.is_encrypted = encrypted
        doc.__iter__ = MagicMock(return_value=iter([mock_page(t) for t in pages]))
        doc.close = MagicMock()
        return doc

    def test_happy_path_returns_text(self):
        from mosaic.pdf import extract_text

        doc = self._make_mock_doc(["Page one text.", "Page two text."])
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = doc
        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            result = extract_text("/some/file.pdf")
        assert "Page one text." in result
        assert "Page two text." in result

    def test_encrypted_returns_empty(self):
        from mosaic.pdf import extract_text

        doc = self._make_mock_doc([], encrypted=True)
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = doc
        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            result = extract_text("/encrypted.pdf")
        assert result == ""

    def test_exception_returns_empty(self):
        from mosaic.pdf import extract_text

        mock_fitz = MagicMock()
        mock_fitz.open.side_effect = RuntimeError("corrupt PDF")
        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            result = extract_text("/corrupt.pdf")
        assert result == ""

    def test_missing_fitz_raises_import_error(self):
        from mosaic.pdf import extract_text

        with patch.dict("sys.modules", {"fitz": None}):
            with pytest.raises(ImportError, match="pymupdf"):
                extract_text("/some/file.pdf")


class TestPdfMagic:
    def test_header_at_offset_zero(self):
        from mosaic.pdf import has_pdf_header

        assert has_pdf_header(b"%PDF-1.7\n...")

    def test_header_after_leading_junk(self):
        from mosaic.pdf import has_pdf_header

        assert has_pdf_header(b"\xef\xbb\xbf\n%PDF-1.4")

    def test_html_rejected(self):
        from mosaic.pdf import has_pdf_header

        assert not has_pdf_header(b"<!DOCTYPE html><html>")

    def test_header_beyond_window_rejected(self):
        from mosaic.pdf import HEADER_WINDOW, has_pdf_header

        assert not has_pdf_header(b" " * HEADER_WINDOW + b"%PDF-1.7")

    def test_is_pdf_file_missing_path(self, tmp_path):
        from mosaic.pdf import is_pdf_file

        assert not is_pdf_file(tmp_path / "nope.pdf")
        assert not is_pdf_file("")
