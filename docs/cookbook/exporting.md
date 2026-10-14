---
title: Exporting
---

# Exporting

Recipes for moving papers out of mosaic: reference files, citations, notes, reference managers and NotebookLM.

[[toc]]

## BibTeX for LaTeX

```bash
mosaic search "hall thruster particle-in-cell" --cached --output refs.bib
```

`@article` for journal papers, `@misc` for preprints; the cite key joins the first author's family name, the year
and the first word of the title. arXiv papers get `eprint` and `eprinttype`. `--output` works on live searches,
`--cached` and `--semantic` searches, and `mosaic similar`.
Tutorial: [exporting](/tutorial/06-exporting).

## RIS for EndNote, Mendeley or Zotero

```bash
mosaic search "hall thruster" --cached -o refs.ris
```

`JOUR` entries for papers with a journal, `GEN` for the others, one `AU` line per author.

## Several formats in one run

```bash
mosaic search "hall thruster" --cached -o refs.bib -o refs.csv -o reading-list.markdown
```

Repeat `--output`; the extension picks the format: `.bib`, `.ris`, `.csv`, `.json`, `.md` (one table) or
`.markdown` (one section per paper, with the abstract).

## A spreadsheet

```bash
mosaic search "hall thruster" --cached --sort citations -o hall.csv
```

One row per paper: title, authors (separated by `;`), year, DOI, arXiv ID, journal, volume, issue, pages, source,
open access, citation count, PDF URL and URL.

## One citation, in APA, on the clipboard

```bash
mosaic cite 10.3389/fphy.2019.00140 --style apa --copy
```

The styles are `bibtex` (the default, from the cache or Crossref metadata), `apa`, `mla`, `chicago`, `harvard`
and `vancouver` (formatted by Crossref, so they need the network). `--copy` also puts the text on the clipboard;
when no clipboard tool is available, mosaic says so and prints the citation only.

## The whole cache to a file

```bash
mosaic cache export library.bib
mosaic cache export thrusters.csv --query "hall thruster" --limit 200
```

`cache export` writes cached papers, newest first, in any of the six formats. `--query` keeps the papers whose
title or abstract contains every word; `--limit` caps the count (0, the default, means all).
Guide: [The cache](/guide/cache#export).

## Obsidian notes

```bash
mosaic config --obsidian-vault ~/vault
mosaic search "hall thruster particle-in-cell" --cached --obsidian
mosaic similar 10.1063/1.4972269 --obsidian --obsidian-folder "papers/related"
```

One note per paper, in the vault's `papers/` folder unless `--obsidian-folder` names another for the run: YAML
front matter (title, authors, year, DOI, journal, links, tags), then the abstract. A note that exists is skipped,
so your edits survive later exports.
Guide: [Obsidian](/guide/obsidian).

## A Zotero collection

```bash
mosaic search "hall thruster" --cached --zotero --zotero-collection "Hall thrusters"
mosaic config --zotero-key KEY                                     # use the web API instead
mosaic search "hall thruster" --cached --zotero --zotero-local     # desktop even with a key
```

Without a key mosaic talks to Zotero desktop, which must be running; with `--download` it also links the PDFs to
the items. With a key it uses the web API, metadata only. The collection is created if missing. mosaic does not
check for duplicates: the same export twice adds the items twice.
Guide: [Zotero](/guide/zotero).

## A NotebookLM notebook

```bash
mosaic notebook create "Hall thrusters" --query "hall thruster anomalous transport" --oa-only --max 10
mosaic notebook create "Hall thruster reading list" --from-dir ~/mosaic-papers --briefing --mind-map
```

The notebook gets the PDFs of a search (`--query`, with the filters of `mosaic search`) or of a folder
(`--from-dir`). Flags such as `--podcast`, `--video`, `--briefing`, `--study-guide`, `--quiz`, `--flashcards`,
`--infographic`, `--slide-deck`, `--data-table` and `--mind-map` ask NotebookLM to generate that material. Needs
the `notebooklm` extra and a one-time `notebooklm login`.
Guide: [NotebookLM](/guide/notebooklm).
