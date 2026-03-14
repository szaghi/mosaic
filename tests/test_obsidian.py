"""Tests for mosaic.obsidian — Obsidian vault note generation."""

from __future__ import annotations

import pytest

from mosaic.models import Paper
from mosaic.obsidian import ObsidianVault, _frontmatter, _yaml_str

# ── _yaml_str ────────────────────────────────────────────────────────────────


def test_yaml_str_plain():
    assert _yaml_str("hello world") == "hello world"


def test_yaml_str_empty_quotes():
    assert _yaml_str("") == '""'


def test_yaml_str_leading_colon():
    assert _yaml_str(": foo") == '": foo"'


def test_yaml_str_contains_colon():
    assert _yaml_str("foo: bar") == '"foo: bar"'


def test_yaml_str_contains_hash():
    assert _yaml_str("foo #bar") == '"foo #bar"'


def test_yaml_str_contains_newline():
    result = _yaml_str("line1\nline2")
    assert "\n" not in result
    assert result.startswith('"')


def test_yaml_str_leading_dash():
    assert _yaml_str("- item") == '"- item"'


def test_yaml_str_leading_quote():
    assert _yaml_str('"quoted"') == '"\\"quoted\\""'


def test_yaml_str_leading_whitespace():
    assert _yaml_str(" spaces") == '" spaces"'


# ── _frontmatter ─────────────────────────────────────────────────────────────


def test_frontmatter_string():
    fm = _frontmatter({"title": "My Paper"})
    assert fm == "---\ntitle: My Paper\n---"


def test_frontmatter_int():
    fm = _frontmatter({"year": 2024})
    assert "year: 2024" in fm


def test_frontmatter_bool_true():
    fm = _frontmatter({"open_access": True})
    assert "open_access: true" in fm


def test_frontmatter_bool_false():
    fm = _frontmatter({"open_access": False})
    assert "open_access: false" in fm


def test_frontmatter_list():
    fm = _frontmatter({"tags": ["paper", "ml"]})
    assert "tags:" in fm
    assert "  - paper" in fm
    assert "  - ml" in fm


def test_frontmatter_wrapped():
    fm = _frontmatter({"title": "T"})
    assert fm.startswith("---\n")
    assert fm.endswith("\n---")


# ── ObsidianVault helpers ─────────────────────────────────────────────────────


@pytest.fixture
def vault(tmp_path):
    return ObsidianVault(vault_path=tmp_path, subfolder="papers")


@pytest.fixture
def simple_paper():
    return Paper(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017,
        doi="10.48550/arxiv.1706.03762",
        arxiv_id="1706.03762",
        abstract="We propose the Transformer architecture.",
        journal="NeurIPS",
        pdf_url="https://arxiv.org/pdf/1706.03762",
        url="https://arxiv.org/abs/1706.03762",
        source="arXiv",
        is_open_access=True,
        citation_count=50000,
    )


def test_notes_dir_with_subfolder(tmp_path):
    v = ObsidianVault(tmp_path, subfolder="papers")
    assert v.notes_dir == tmp_path / "papers"


def test_notes_dir_no_subfolder(tmp_path):
    v = ObsidianVault(tmp_path, subfolder="")
    assert v.notes_dir == tmp_path


def test_note_stem_no_pdf_suffix(vault, simple_paper):
    stem = vault.note_stem(simple_paper)
    assert not stem.endswith(".pdf")
    assert not stem.endswith(".md")


def test_note_path_has_md_extension(vault, simple_paper):
    path = vault.note_path(simple_paper)
    assert path.suffix == ".md"
    assert path.parent == vault.notes_dir


def test_note_exists_false_before_export(vault, simple_paper):
    assert not vault.note_exists(simple_paper)


# ── ObsidianVault.export_papers ───────────────────────────────────────────────


def test_export_creates_dir(tmp_path, simple_paper):
    v = ObsidianVault(tmp_path, subfolder="mynotes")
    assert not (tmp_path / "mynotes").exists()
    v.export_papers([simple_paper])
    assert (tmp_path / "mynotes").is_dir()


def test_export_returns_added_skipped(vault, simple_paper):
    added, skipped = vault.export_papers([simple_paper])
    assert added == 1
    assert skipped == 0


def test_export_skips_existing(vault, simple_paper):
    vault.export_papers([simple_paper])
    added, skipped = vault.export_papers([simple_paper])
    assert added == 0
    assert skipped == 1


def test_export_creates_file(vault, simple_paper):
    vault.export_papers([simple_paper])
    assert vault.note_path(simple_paper).exists()


def test_export_multiple(vault, simple_paper):
    p2 = Paper(title="BERT", authors=["Jacob Devlin"], year=2019, source="arXiv")
    added, skipped = vault.export_papers([simple_paper, p2])
    assert added == 2
    assert skipped == 0


# ── rendered content ──────────────────────────────────────────────────────────


@pytest.fixture
def rendered(vault, simple_paper):
    vault.export_papers([simple_paper])
    return vault.note_path(simple_paper).read_text(encoding="utf-8")


def test_render_has_frontmatter(rendered):
    assert rendered.startswith("---\n")
    assert "---" in rendered


def test_render_frontmatter_title(rendered, simple_paper):
    assert f"title: {simple_paper.title}" in rendered


def test_render_frontmatter_year(rendered):
    assert "year: 2017" in rendered


def test_render_frontmatter_doi(rendered):
    assert "doi:" in rendered


def test_render_frontmatter_arxiv_id(rendered):
    assert "arxiv_id:" in rendered


def test_render_frontmatter_source(rendered):
    assert "source: arXiv" in rendered


def test_render_frontmatter_open_access(rendered):
    assert "open_access: true" in rendered


def test_render_frontmatter_citation_count(rendered):
    assert "citation_count: 50000" in rendered


def test_render_frontmatter_tags(rendered):
    assert "tags:" in rendered
    assert "  - paper" in rendered


def test_render_h1_title(rendered, simple_paper):
    assert f"# {simple_paper.title}" in rendered


def test_render_abstract_callout(rendered):
    assert "> [!abstract]" in rendered
    assert "> We propose" in rendered


def test_render_metadata_table(rendered):
    assert "## Metadata" in rendered
    assert "| Field | Value |" in rendered
    assert "| Authors |" in rendered
    assert "| Year | 2017 |" in rendered


def test_render_pdf_link(rendered):
    assert "| PDF |" in rendered
    assert "[link](" in rendered


def test_render_url_link(rendered):
    assert "| URL |" in rendered


def test_render_no_template_syntax(rendered):
    assert "{{" not in rendered
    assert "}}" not in rendered
    assert "<%" not in rendered
    assert "%>" not in rendered


def test_render_ends_with_newline(rendered):
    assert rendered.endswith("\n")


# ── wikilinks ────────────────────────────────────────────────────────────────


def test_wikilinks_in_batch(tmp_path):
    v = ObsidianVault(tmp_path, subfolder="", wikilinks=True)
    p1 = Paper(title="Alpha Paper", authors=["A. Author"], year=2020, source="arXiv")
    p2 = Paper(title="Beta Paper", authors=["B. Author"], year=2021, source="arXiv")
    v.export_papers([p1, p2])

    note1 = v.note_path(p1).read_text()
    note2 = v.note_path(p2).read_text()

    stem2 = v.note_stem(p2)
    stem1 = v.note_stem(p1)

    assert f"[[{stem2}]]" in note1
    assert f"[[{stem1}]]" in note2


def test_no_wikilinks_single_paper(tmp_path, simple_paper):
    v = ObsidianVault(tmp_path, subfolder="", wikilinks=True)
    v.export_papers([simple_paper])
    content = v.note_path(simple_paper).read_text()
    assert "## See also" not in content


def test_wikilinks_disabled(tmp_path):
    v = ObsidianVault(tmp_path, subfolder="", wikilinks=False)
    p1 = Paper(title="Alpha Paper", authors=["A"], year=2020, source="arXiv")
    p2 = Paper(title="Beta Paper", authors=["B"], year=2021, source="arXiv")
    v.export_papers([p1, p2])
    note1 = v.note_path(p1).read_text()
    assert "## See also" not in note1


def test_wikilinks_see_also_section(tmp_path):
    v = ObsidianVault(tmp_path, subfolder="", wikilinks=True)
    p1 = Paper(title="Alpha Paper", authors=["A"], year=2020, source="arXiv")
    p2 = Paper(title="Beta Paper", authors=["B"], year=2021, source="arXiv")
    v.export_papers([p1, p2])
    note1 = v.note_path(p1).read_text()
    assert "## See also" in note1


# ── custom config ─────────────────────────────────────────────────────────────


def test_custom_tags(tmp_path, simple_paper):
    v = ObsidianVault(tmp_path, subfolder="", tags=["research", "ml"])
    v.export_papers([simple_paper])
    content = v.note_path(simple_paper).read_text()
    assert "  - research" in content
    assert "  - ml" in content


def test_default_tags(tmp_path, simple_paper):
    v = ObsidianVault(tmp_path, subfolder="")
    v.export_papers([simple_paper])
    content = v.note_path(simple_paper).read_text()
    assert "  - paper" in content


def test_custom_filename_pattern(tmp_path, simple_paper):
    v = ObsidianVault(tmp_path, subfolder="", filename_pattern="{author}_{year}")
    stem = v.note_stem(simple_paper)
    assert "2017" in stem
    assert stem.endswith(".pdf") is False


# ── minimal paper (sparse fields) ────────────────────────────────────────────


def test_minimal_paper_no_abstract(tmp_path):
    paper = Paper(title="Minimal Paper", source="arXiv")
    v = ObsidianVault(tmp_path, subfolder="")
    v.export_papers([paper])
    content = v.note_path(paper).read_text()
    assert "> [!abstract]" not in content
    assert "# Minimal Paper" in content


def test_minimal_paper_no_authors(tmp_path):
    paper = Paper(title="No Authors", source="DOAJ")
    v = ObsidianVault(tmp_path, subfolder="")
    v.export_papers([paper])
    content = v.note_path(paper).read_text()
    assert "authors:" not in content
    assert "| Authors |" not in content


def test_minimal_paper_no_doi(tmp_path):
    paper = Paper(title="No DOI Paper", source="BASE")
    v = ObsidianVault(tmp_path, subfolder="")
    v.export_papers([paper])
    content = v.note_path(paper).read_text()
    assert "doi:" not in content


def test_open_access_false_not_in_table(tmp_path):
    paper = Paper(title="Closed Paper", source="Scopus", is_open_access=False)
    v = ObsidianVault(tmp_path, subfolder="")
    v.export_papers([paper])
    content = v.note_path(paper).read_text()
    assert "| Open Access |" not in content


def test_volume_issue_pages_in_note(tmp_path):
    paper = Paper(
        title="Journal Article",
        source="CrossRef",
        volume="42",
        issue="3",
        pages="100-120",
    )
    v = ObsidianVault(tmp_path, subfolder="")
    v.export_papers([paper])
    content = v.note_path(paper).read_text()
    assert "volume: 42" in content
    assert "issue: 3" in content
    assert "pages: 100-120" in content
    assert "| Volume | 42 |" in content
    assert "| Issue | 3 |" in content
    assert "| Pages | 100-120 |" in content
