"""Tests for the export module."""

import csv
import json

import pytest

from mosaic.exporter import export
from mosaic.models import Paper

_PAPERS = [
    Paper(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017,
        doi="10.48550/arXiv.1706.03762",
        arxiv_id="1706.03762",
        abstract="We propose the Transformer.",
        journal="NeurIPS",
        volume="30",
        issue=None,
        pages="1-11",
        source="arXiv",
        is_open_access=True,
        pdf_url="https://arxiv.org/pdf/1706.03762",
        url="https://arxiv.org/abs/1706.03762",
    ),
    Paper(
        title="BERT: Pre-training of Deep Bidirectional Transformers",
        authors=["Jacob Devlin"],
        year=2019,
        doi=None,
        arxiv_id="1810.04805",
        journal=None,
        source="arXiv",
        is_open_access=True,
        pdf_url="https://arxiv.org/pdf/1810.04805",
    ),
]


class TestMarkdown:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "results.md"
        export(_PAPERS, out)
        assert out.exists()

    def test_header_row(self, tmp_path):
        out = tmp_path / "results.md"
        export(_PAPERS, out)
        lines = out.read_text().splitlines()
        assert "Title" in lines[0]
        assert "DOI" in lines[0]

    def test_contains_paper_data(self, tmp_path):
        out = tmp_path / "results.md"
        export(_PAPERS, out)
        text = out.read_text()
        assert "Attention Is All You Need" in text
        assert "10.48550/arXiv.1706.03762" in text
        assert "Vaswani" in text

    def test_row_count(self, tmp_path):
        out = tmp_path / "results.md"
        export(_PAPERS, out)
        data_lines = [
            line
            for line in out.read_text().splitlines()
            if line.startswith("|") and "---" not in line and "Title" not in line
        ]
        assert len(data_lines) == len(_PAPERS)


class TestMarkdownFull:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "results.markdown"
        export(_PAPERS, out)
        assert out.exists()

    def test_each_paper_has_subsection(self, tmp_path):
        out = tmp_path / "results.markdown"
        export(_PAPERS, out)
        text = out.read_text()
        assert "## 1. Attention Is All You Need" in text
        assert "## 2. BERT" in text

    def test_all_fields_present(self, tmp_path):
        out = tmp_path / "results.markdown"
        export(_PAPERS, out)
        text = out.read_text()
        assert "10.48550/arXiv.1706.03762" in text
        assert "1706.03762" in text
        assert "NeurIPS" in text
        assert "We propose the Transformer." in text
        assert "arxiv.org/pdf/1706.03762" in text
        assert "Open Access" in text

    def test_papers_separated_by_hr(self, tmp_path):
        out = tmp_path / "results.markdown"
        export(_PAPERS, out)
        assert "---" in out.read_text()

    def test_empty_fields_omitted(self, tmp_path):
        out = tmp_path / "results.markdown"
        export(_PAPERS, out)
        # second paper has no journal — row should not appear
        lines = out.read_text().splitlines()
        bert_start = next(i for i, line in enumerate(lines) if "BERT" in line)
        bert_block = "\n".join(lines[bert_start:])
        assert "| Journal |" not in bert_block


class TestCSV:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "results.csv"
        export(_PAPERS, out)
        assert out.exists()

    def test_header_columns(self, tmp_path):
        out = tmp_path / "results.csv"
        export(_PAPERS, out)
        with out.open() as fh:
            reader = csv.DictReader(fh)
            assert "title" in reader.fieldnames
            assert "doi" in reader.fieldnames
            assert "authors" in reader.fieldnames

    def test_authors_joined_with_semicolon(self, tmp_path):
        out = tmp_path / "results.csv"
        export(_PAPERS, out)
        with out.open() as fh:
            rows = list(csv.DictReader(fh))
        assert rows[0]["authors"] == "Ashish Vaswani; Noam Shazeer"

    def test_row_count(self, tmp_path):
        out = tmp_path / "results.csv"
        export(_PAPERS, out)
        with out.open() as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == len(_PAPERS)

    def test_missing_fields_empty_string(self, tmp_path):
        out = tmp_path / "results.csv"
        export(_PAPERS, out)
        with out.open() as fh:
            rows = list(csv.DictReader(fh))
        assert rows[1]["doi"] == ""
        assert rows[1]["journal"] == ""


class TestJSON:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "results.json"
        export(_PAPERS, out)
        assert out.exists()

    def test_valid_json(self, tmp_path):
        out = tmp_path / "results.json"
        export(_PAPERS, out)
        data = json.loads(out.read_text())
        assert isinstance(data, list)

    def test_record_count(self, tmp_path):
        out = tmp_path / "results.json"
        export(_PAPERS, out)
        data = json.loads(out.read_text())
        assert len(data) == len(_PAPERS)

    def test_authors_as_list(self, tmp_path):
        out = tmp_path / "results.json"
        export(_PAPERS, out)
        data = json.loads(out.read_text())
        assert isinstance(data[0]["authors"], list)
        assert "Ashish Vaswani" in data[0]["authors"]

    def test_all_fields_present(self, tmp_path):
        out = tmp_path / "results.json"
        export(_PAPERS, out)
        data = json.loads(out.read_text())
        for key in ("title", "authors", "year", "doi", "abstract", "journal", "source"):
            assert key in data[0]


class TestBibTeX:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        assert out.exists()

    def test_article_type_for_journal_paper(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        text = out.read_text()
        assert "@article{" in text

    def test_misc_type_for_preprint(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        text = out.read_text()
        assert "@misc{" in text

    def test_contains_doi(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        assert "10.48550/arXiv.1706.03762" in out.read_text()

    def test_cite_key_format(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        text = out.read_text()
        assert "Vaswani2017Attention" in text

    def test_arxiv_howpublished_for_preprint(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        text = out.read_text()
        assert "arXiv:1810.04805" in text

    def test_eprint_and_eprinttype(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        text = out.read_text()
        assert "eprint" in text
        assert "eprinttype" in text
        assert "arXiv" in text

    def test_abstract_included(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        assert "We propose the Transformer." in out.read_text()

    def test_pdf_url_included(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        assert "arxiv.org/pdf/1706.03762" in out.read_text()

    def test_open_access_note(self, tmp_path):
        out = tmp_path / "results.bib"
        export(_PAPERS, out)
        assert "Open Access" in out.read_text()


class TestRIS:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        assert out.exists()

    def test_ty_jour_for_journal_paper(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        text = out.read_text()
        assert "TY  - JOUR" in text

    def test_ty_gen_for_preprint(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        text = out.read_text()
        assert "TY  - GEN" in text

    def test_title_field(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        assert "TI  - Attention Is All You Need" in out.read_text()

    def test_author_per_line(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        text = out.read_text()
        assert "AU  - Ashish Vaswani" in text
        assert "AU  - Noam Shazeer" in text

    def test_year_field(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        assert "PY  - 2017" in out.read_text()

    def test_journal_field(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        assert "JO  - NeurIPS" in out.read_text()

    def test_doi_field(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        assert "DO  - 10.48550/arXiv.1706.03762" in out.read_text()

    def test_abstract_field(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        assert "AB  - We propose the Transformer." in out.read_text()

    def test_pages_split_into_sp_ep(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        text = out.read_text()
        assert "SP  - 1" in text
        assert "EP  - 11" in text

    def test_url_field(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        assert "UR  - https://arxiv.org/abs/1706.03762" in out.read_text()

    def test_pdf_url_fallback_when_no_url(self, tmp_path):
        # BERT paper has pdf_url but no url
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        text = out.read_text()
        assert "UR  - https://arxiv.org/pdf/1810.04805" in text

    def test_each_record_ends_with_er(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        text = out.read_text()
        assert text.count("ER  - ") == len(_PAPERS)

    def test_record_count(self, tmp_path):
        out = tmp_path / "results.ris"
        export(_PAPERS, out)
        text = out.read_text()
        assert text.count("TY  - ") == len(_PAPERS)


class TestDispatch:
    def test_unsupported_extension_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported format"):
            export(_PAPERS, tmp_path / "results.txt")
