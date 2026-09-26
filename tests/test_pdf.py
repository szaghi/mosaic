"""Tests for mosaic/pdf.py -- PDF text extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestIsAvailable:
    def test_returns_true_when_fitz_importable(self):
        from mosaic.pdf import is_available

        mock_fitz = MagicMock()
        with patch.dict("sys.modules", {"pymupdf": mock_fitz, "fitz": mock_fitz}):
            assert is_available() is True

    def test_returns_false_when_fitz_missing(self):
        from mosaic.pdf import is_available

        with patch.dict("sys.modules", {"pymupdf": None, "fitz": None}):
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
        with patch.dict("sys.modules", {"pymupdf": mock_fitz, "fitz": mock_fitz}):
            result = extract_text("/some/file.pdf")
        assert "Page one text." in result
        assert "Page two text." in result

    def test_encrypted_returns_empty(self):
        from mosaic.pdf import extract_text

        doc = self._make_mock_doc([], encrypted=True)
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = doc
        with patch.dict("sys.modules", {"pymupdf": mock_fitz, "fitz": mock_fitz}):
            result = extract_text("/encrypted.pdf")
        assert result == ""

    def test_exception_returns_empty(self):
        from mosaic.pdf import extract_text

        mock_fitz = MagicMock()
        mock_fitz.open.side_effect = RuntimeError("corrupt PDF")
        with patch.dict("sys.modules", {"pymupdf": mock_fitz, "fitz": mock_fitz}):
            result = extract_text("/corrupt.pdf")
        assert result == ""

    def test_document_closed_on_every_path(self):
        from mosaic.pdf import extract_text

        encrypted = self._make_mock_doc([], encrypted=True)
        broken = self._make_mock_doc([])
        broken.__iter__ = MagicMock(side_effect=RuntimeError("bad page tree"))
        ok = self._make_mock_doc(["text"])
        for doc, expected in ((encrypted, ""), (broken, ""), (ok, "text")):
            mock_fitz = MagicMock()
            mock_fitz.open.return_value = doc
            with patch.dict("sys.modules", {"pymupdf": mock_fitz, "fitz": mock_fitz}):
                assert extract_text("/x.pdf") == expected
            doc.close.assert_called_once()

    def test_page_cap(self):
        from mosaic.pdf import extract_text

        doc = self._make_mock_doc([f"page{i}" for i in range(10)])
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = doc
        with patch.dict("sys.modules", {"pymupdf": mock_fitz, "fitz": mock_fitz}):
            result = extract_text("/big.pdf", max_pages=3)
        assert "page2" in result
        assert "page3" not in result

    def test_missing_fitz_raises_import_error(self):
        from mosaic.pdf import extract_text

        with patch.dict("sys.modules", {"pymupdf": None, "fitz": None}):
            with pytest.raises(ImportError, match="pymupdf"):
                extract_text("/some/file.pdf")
