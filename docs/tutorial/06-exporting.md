---
pageClass: tutorial-page
aside: false
title: 6. Exporting
---

# 6. Exporting

The results live in the cache; your other tools want files. `--output` (`-o`) writes the papers a search shows, in
the format the extension names, and you can repeat it:

<<< @/examples/output/06/output.txt{console}

| Extension | Format | For |
|---|---|---|
| `.bib` | BibTeX: `@article` for journal papers, `@misc` for preprints | LaTeX, JabRef, Zotero |
| `.ris` | RIS | EndNote, Mendeley, RefWorks, Zotero |
| `.csv` | one row per paper, authors separated by `;` | spreadsheets |
| `.json` | an array of paper objects | scripts |
| `.md` | one Markdown table | a README, a wiki |
| `.markdown` | one Markdown section per paper, with the abstract | notes |

<<< @/examples/output/06/bib.txt{console}

A cite key joins the first author's family name, the year and the first word of the title. arXiv papers get
`eprint` and `eprinttype`, open-access papers a `pdf` field and `note = {Open Access}`. `--output` works the same
with a live search, with `--cached` as here, and with `mosaic similar`.

## One citation

<<< @/examples/output/06/cite.txt{console}

`mosaic cite` formats one paper by DOI. `bibtex`, the default, is built from the cache or from Crossref's
metadata; `apa`, `mla`, `chicago`, `harvard` and `vancouver` come from Crossref's formatter, so they need the
network. `--copy` (`-c`) also puts the text on the clipboard.

## JSON for scripts

`--json` prints the results as one JSON document on standard output, in place of the table, ready for `jq`:

<<< @/examples/output/06/json.txt{console}

The document holds `status`, `query`, `count`, `papers` and `errors` (the sources that failed);
[Agents and Claude Code](/guide/agent-workflows) describes every field.

## Obsidian notes

Point mosaic at a vault once, then add `--obsidian` to a search:

```bash
mosaic config --obsidian-vault ~/vault
```

<<< @/examples/output/06/obsidian.txt{console}

<<< @/examples/output/06/note.txt{console}

Each paper becomes a note in `papers/` (`--obsidian-folder` changes it): YAML front matter with title, authors,
year, DOI, journal, links and tags, then the abstract. A note that exists is skipped, so your annotations stay.
[Obsidian](/guide/obsidian) shows a full note and the options.

## Zotero

`--zotero` sends the results to your Zotero library: to the desktop app through its local API while Zotero runs,
or through the web API with a key (`mosaic config --zotero-key`). `--zotero-collection NAME` files them in a
collection, created if missing; with `--download`, the local API also links the PDFs.

```bash
mosaic search "hall thruster particle-in-cell" --cached --zotero --zotero-collection "Hall thrusters"
```

[Zotero](/guide/zotero) covers the setup.

::: tip What you learned
`--output` in six formats, `mosaic cite`, `--json`, `--obsidian`, `--zotero`. Reference:
[`search`](/reference/search), [`cite`](/reference/cite).
:::

Next: [7. Following a field](./07-following).
