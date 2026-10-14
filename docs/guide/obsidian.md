---
title: Obsidian
---

# Obsidian

`--obsidian` writes one Markdown note per paper into an [Obsidian](https://obsidian.md) vault: the metadata as
Obsidian properties, the abstract, and links to the other papers of the same export. Use it to build a
literature vault you annotate by hand.

## Usage

Point mosaic at the vault once:

```bash
mosaic config --obsidian-vault ~/vault
```

Then add `--obsidian` to `search`, `similar` or `get`:

```bash
mosaic search "hall thruster particle-in-cell" --cached --obsidian
mosaic similar 10.1063/1.4972269 --obsidian
mosaic get 10.3389/fphy.2019.00140 --obsidian
mosaic search "hall thruster" --obsidian --obsidian-folder "papers/hall"   # another subfolder, this run only
```

The run ends with a count and the folder:

```
Obsidian: 29 note(s) added → ~/vault/papers
```

A note that already exists is skipped (`N skipped (already exist)`): mosaic never overwrites a note, so your
edits survive later exports.

## The note

This note was written by the export of [tutorial chapter 6](/tutorial/06-exporting) (abstract and links
shortened):

````markdown
---
title: "E × B electron drift instability in Hall thrusters: Particle-in-cell simulations vs. theory"
authors:
  - Jean-Pierre Bœuf
  - Laurent Garrigues
year: 2018
doi: 10.1063/1.5017033
journal: Physics of Plasmas
volume: 25
issue: 6
source: OpenAlex
open_access: true
citation_count: 144
pdf_url: "https://aip.scitation.org/doi/pdf/10.1063/1.5017033"
url: "https://openalex.org/W2804872065"
tags:
  - paper
---

# E × B electron drift instability in Hall thrusters: Particle-in-cell simulations vs. theory

> [!abstract]
> The E × B Electron Drift Instability (E × B EDI), also called Electron Cyclotron Drift Instability, ...

## Metadata

| Field | Value |
|-------|-------|
| Authors | Jean-Pierre Bœuf, Laurent Garrigues |
| Year | 2018 |
| DOI | 10.1063/1.5017033 |
...

## See also

- [[2023_Maryam_Reduced-order_particle-in-cell_simulations_of_a_high-power_m]]
- [[2019_Zahra_Numerical_Study_of_Electron_Cyclotron_Drift_Instability_Appl]]
...
````

- Properties appear only when the paper has them (no `doi:` line without a DOI); `source`, `open_access` and `tags`
  are always there.
- The abstract callout is omitted when the source gave no abstract.
- See also links every other paper of the same command run, when `wikilinks` is on and the run exported more than
  one paper. Notes of earlier runs are not linked: mosaic does not read the vault.
- Notes contain no <span v-pre>`{{...}}`</span> or `<%...%>`, so the Templates and Templater plugins leave them
  alone. The properties work with Dataview:

````markdown
```dataview
TABLE year, citation_count AS "Citations"
FROM "papers"
WHERE open_access = true
SORT citation_count DESC
```
````

## Configuration

```toml
[obsidian]
vault_path = ""                            # vault root; required
subfolder = "papers"                       # "" writes to the vault root
filename_pattern = "{year}_{author}_{title}"
tags = ["paper"]
wikilinks = true
```

| Key | Set with |
|---|---|
| `vault_path` | `mosaic config --obsidian-vault PATH` |
| `subfolder` | `mosaic config --obsidian-subfolder NAME` (`--obsidian-folder` overrides it for one run) |
| `filename_pattern` | `mosaic config --obsidian-filename-pattern PATTERN` |
| `tags` | `mosaic config --obsidian-tag paper --obsidian-tag hall` (repeatable; replaces the list) |
| `wikilinks` | `mosaic config --obsidian-wikilinks` / `--no-obsidian-wikilinks` |

The file name placeholders are those of PDF file names: `{year}` (`0000` if unknown), `{author}`, `{title}` (the
first 60 characters), `{source}`, `{doi}`, `{journal}`. `{author}` is the first word of the first author's name as
the source writes it: the family name for "Family, Given" sources such as Crossref, the given name for "Given
Family" ones such as arXiv (`2019_Zahra_...` above).

A note is matched by its file name: change `filename_pattern` and the next export writes new notes beside the old
ones.

See also: [tutorial chapter 6](/tutorial/06-exporting), [export recipes](/cookbook/exporting),
[`mosaic config`](/reference/config).
