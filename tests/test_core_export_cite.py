"""BibTeX keys/escaping and citation fetching edge cases."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

from mosaic.cite import _parse_crossref_item, bibtex_citation, fetch_formatted_citation
from mosaic.exporter import _balance_braces, _bib_text, _bibtex_key, export
from mosaic.models import Paper


class TestBibtexKeys:
    def test_colliding_keys_get_suffixes(self, tmp_path):
        papers = [
            Paper(title="Deep residual learning", authors=["Kaiming He"], year=2016),
            Paper(title="Deep networks with stochastic depth", authors=["Gao He"], year=2016),
            Paper(title="Deep something else", authors=["Wei He"], year=2016),
        ]
        out = tmp_path / "r.bib"
        export(papers, out)
        text = out.read_text()
        assert "@misc{He2016Deep," in text
        assert "@misc{He2016Deepa," in text
        assert "@misc{He2016Deepb," in text

    def test_family_given_form_uses_family_name(self):
        assert _bibtex_key(Paper(title="On things", authors=["Doe, John"], year=2020), 1) == (
            "Doe2020On"
        )

    def test_pubmed_initials_form_uses_family_name(self):
        assert _bibtex_key(Paper(title="Deep", authors=["Hinton GE"], year=2015), 1) == (
            "Hinton2015Deep"
        )

    def test_accented_names_transliterated(self):
        assert _bibtex_key(Paper(title="Über", authors=["Jürgen Müller"], year=2015), 1) == (
            "Muller2015Uber"
        )

    def test_blank_first_author_does_not_crash(self):
        assert _bibtex_key(Paper(title="X", authors=["", "Ann Lee"], year=2020), 1) == "Lee2020X"

    def test_single_citation_unchanged(self):
        p = Paper(title="Attention", authors=["Ashish Vaswani"], year=2017, journal="NeurIPS")
        assert bibtex_citation(p).startswith("@article{Vaswani2017Attention,")


class TestBibtexEscaping:
    def test_latex_specials_escaped(self):
        assert _bib_text("Computers & Chemical Engineering") == r"Computers \& Chemical Engineering"
        assert _bib_text("100% of #1 x_y") == r"100\% of \#1 x\_y"

    def test_already_escaped_not_doubled(self):
        assert _bib_text(r"A \& B") == r"A \& B"

    def test_math_segments_left_alone(self):
        assert (
            _bib_text(r"The $\alpha_i$-divergence of x_i") == r"The $\alpha_i$-divergence of x\_i"
        )

    def test_unpaired_dollar_escaped(self):
        assert _bib_text("costs $5 each") == r"costs \$5 each"

    def test_unbalanced_braces_removed(self):
        assert _balance_braces("a } b { c") == "a  b  c"
        assert _balance_braces("{ok} {nested {x}}") == "{ok} {nested {x}}"

    def test_entry_is_brace_balanced(self, tmp_path):
        p = Paper(
            title="Broken {title",
            authors=["A & B Lab"],
            abstract="uses } and % signs",
            journal="J. {Chem",
            year=2020,
        )
        out = tmp_path / "r.bib"
        export([p], out)
        text = out.read_text()
        assert text.count("{") == text.count("}")
        assert r"A \& B Lab" in text
        assert r"\% signs" in text


def _cite_resp(text: str, content_type: str):
    m = MagicMock()
    m.text = text
    m.headers = {"content-type": content_type}
    m.raise_for_status = MagicMock()
    return m


def _client_cm(resp):
    client = MagicMock()
    client.get.return_value = resp
    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    return cm


class TestFormattedCitation:
    def test_html_landing_page_rejected(self):
        resp = _cite_resp("<!DOCTYPE html><html>Publisher page</html>", "text/html; charset=utf-8")
        with patch("mosaic.cite.httpx.Client", return_value=_client_cm(resp)):
            with pytest.raises(ValueError):
                fetch_formatted_citation("10.1/x", "apa")

    def test_html_without_content_type_rejected(self):
        resp = _cite_resp("<html><body>x</body></html>", "")
        with patch("mosaic.cite.httpx.Client", return_value=_client_cm(resp)):
            with pytest.raises(ValueError):
                fetch_formatted_citation("10.1/x", "apa")

    def test_bibliography_accepted(self):
        resp = _cite_resp("Doe, J. (2020). Title. Journal.\n", "text/x-bibliography")
        with patch("mosaic.cite.httpx.Client", return_value=_client_cm(resp)):
            assert fetch_formatted_citation("10.1/x", "apa") == "Doe, J. (2020). Title. Journal."

    def test_plain_text_citation_accepted(self):
        resp = _cite_resp("Doe, J. (2020). Title.", "text/plain")
        with patch("mosaic.cite.httpx.Client", return_value=_client_cm(resp)):
            assert fetch_formatted_citation("10.1/x", "apa").startswith("Doe")

    def test_empty_body_rejected(self):
        resp = _cite_resp("   ", "text/x-bibliography")
        with patch("mosaic.cite.httpx.Client", return_value=_client_cm(resp)):
            with pytest.raises(ValueError):
                fetch_formatted_citation("10.1/x", "apa")


class TestCrossrefOpenAccess:
    _BASE: ClassVar[dict] = {"title": ["T"], "DOI": "10.1/x"}

    def test_cc_license_marks_open_access(self):
        item = {
            **self._BASE,
            "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
            "link": [{"content-type": "application/pdf", "URL": "https://pub/x.pdf"}],
        }
        p = _parse_crossref_item(item)
        assert p.is_open_access is True
        assert p.pdf_url == "https://pub/x.pdf"

    def test_text_mining_link_on_paywalled_paper_ignored(self):
        item = {
            **self._BASE,
            "license": [{"URL": "https://www.elsevier.com/tdm/userlicense/1.0/"}],
            "link": [
                {
                    "content-type": "application/pdf",
                    "URL": "https://api.elsevier.com/x.pdf",
                    "intended-application": "text-mining",
                }
            ],
        }
        p = _parse_crossref_item(item)
        assert p.is_open_access is False
        assert p.pdf_url is None

    def test_prefers_non_restricted_pdf_link(self):
        item = {
            **self._BASE,
            "license": [{"URL": "http://creativecommons.org/licenses/by/4.0"}],
            "link": [
                {
                    "content-type": "application/pdf",
                    "URL": "https://tdm/x.pdf",
                    "intended-application": "text-mining",
                },
                {"content-type": "application/pdf", "URL": "https://pub/x.pdf"},
            ],
        }
        assert _parse_crossref_item(item).pdf_url == "https://pub/x.pdf"

    def test_text_mining_link_used_when_oa_and_only_option(self):
        item = {
            **self._BASE,
            "license": [{"URL": "http://creativecommons.org/licenses/by/4.0"}],
            "link": [
                {
                    "content-type": "application/pdf",
                    "URL": "https://tdm/x.pdf",
                    "intended-application": "text-mining",
                }
            ],
        }
        assert _parse_crossref_item(item).pdf_url == "https://tdm/x.pdf"


def test_markdown_export_path_type(tmp_path: Path):
    # Sanity: export() still dispatches after the BibTeX refactor
    export([Paper(title="T")], tmp_path / "r.md")
    assert (tmp_path / "r.md").exists()
