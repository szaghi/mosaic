---
title: Obsidian Integration
---

# Obsidian Integration

MOSAIC can write paper notes directly into an [Obsidian](https://obsidian.md) vault. Each paper becomes one `.md` file with:

- **YAML frontmatter** — Obsidian *Properties* (title, authors, year, DOI, …)
- **Abstract callout** — `> [!abstract]` block
- **Metadata table** — human-readable field/value pairs
- **See also** — `[[wikilinks]]` to other papers exported in the same batch

Notes already present in the vault are never overwritten, preserving any manual edits.

## Setup

Add the vault path to your config file:

```toml
# ~/.config/mosaic/config.toml
[obsidian]
vault_path = "/path/to/your/vault"   # required
subfolder  = "papers"                # optional, default: "papers"
```

Or use the full reference below to customise every option.

## Usage

Add `--obsidian` to any `search`, `similar`, or `get` command:

```bash
# Export search results as Obsidian notes
mosaic search "transformer attention" --obsidian

# Export and also download PDFs
mosaic search "BERT NLP" --obsidian --download

# Find similar papers and export them
mosaic similar 10.48550/arxiv.1706.03762 --obsidian

# Download a paper by DOI and create a note
mosaic get 10.1234/example --obsidian

# Write notes to a different subfolder this run
mosaic search "diffusion models" --obsidian --obsidian-folder "AI/diffusion"
```

![Obsidian integration demo](/gifs/13_obsidian.gif)

## Note format

A generated note looks like this:

````markdown
---
title: Attention Is All You Need
authors:
  - Ashish Vaswani
  - Noam Shazeer
year: 2017
doi: 10.48550/arxiv.1706.03762
arxiv_id: 1706.03762
journal: NeurIPS
source: arXiv
open_access: true
citation_count: 50000
pdf_url: https://arxiv.org/pdf/1706.03762
tags:
  - paper
---

# Attention Is All You Need

> [!abstract]
> We propose a new simple network architecture, the Transformer, …

## Metadata

| Field | Value |
|-------|-------|
| Authors | Ashish Vaswani, Noam Shazeer |
| Year | 2017 |
| DOI | 10.48550/arxiv.1706.03762 |
| Source | arXiv |
| Open Access | yes |
| Citations | 50000 |
| URL | [link](https://arxiv.org/abs/1706.03762) |
| PDF | [link](https://arxiv.org/pdf/1706.03762) |

## See also

- [[2019_Devlin_BERT pre-training of deep bidirectional transformers]]
- [[2020_Brown_Language models are few-shot learners]]
````

### Plugin compatibility

| Plugin | Compatible | Notes |
|---|---|---|
| **Obsidian Properties** (core) | ✅ | YAML frontmatter is standard Obsidian property format |
| **Dataview** (community) | ✅ | Query by `year`, `doi`, `source`, `citation_count`, etc. |
| **Templates** (core) | ✅ | Notes contain no <span v-pre>`{{…}}`</span> syntax — not processed as templates |
| **Templater** (community) | ✅ | Notes contain no `<%…%>` syntax — not processed as templates |

## Configuration reference

```toml
[obsidian]
# Absolute path to the Obsidian vault root directory (required)
vault_path = "/home/you/my-vault"

# Subfolder within the vault where paper notes are written
# Use "" to write notes directly to the vault root
subfolder = "papers"

# Filename pattern — same placeholders as the PDF filename pattern:
#   {year}    publication year (0000 if unknown)
#   {author}  first author last name
#   {title}   title slug, truncated to 60 chars
#   {source}  source name (arXiv, Scopus, …)
#   {doi}     DOI with special chars replaced by _
#   {journal} journal name slug (no_journal if unknown)
filename_pattern = "{year}_{author}_{title}"

# Tags added to every note's frontmatter
tags = ["paper"]

# When true, a "See also" section with [[wikilinks]] is added to each note,
# linking to the other papers exported in the same command invocation
wikilinks = true
```

## Deduplication

Notes are never overwritten. If a note file for a paper already exists (matched by filename), it is silently skipped. This means any annotations, links, or edits you have added to the note are preserved across future exports.

The `export_papers` call returns `(added, skipped)` counts, which MOSAIC prints after each run:

```
Obsidian: 8 note(s) added, 2 skipped (already exist) → /home/you/my-vault/papers
```

## Wikilinks

When `wikilinks = true` (the default), each exported note gets a **See also** section listing `[[wikilinks]]` to the other papers exported in the **same command invocation**. Links are not added across separate runs — MOSAIC does not scan the whole vault.

To disable wikilinks entirely:

```toml
[obsidian]
wikilinks = false
```

## Dataview queries

Because each note's frontmatter is standard Obsidian Properties, you can query your paper collection with the [Dataview](https://blacksmithgu.github.io/obsidian-dataview/) community plugin. Examples:

````
```dataview
TABLE year, authors, citation_count AS "Citations"
FROM "papers"
WHERE source = "arXiv"
SORT citation_count DESC
```
````

````
```dataview
LIST
FROM "papers"
WHERE year >= 2022 AND open_access = true
SORT year DESC
```
````
