---
title: Usage
---

# Usage

## Basic search

```bash
mosaic search "transformer attention mechanism"
```

Queries all enabled sources and prints a results table:

```
 #   Title                          Authors          Year   Source            OA    PDF
 1   Attention Is All You Need      Vaswani et al.   2017   Semantic Scholar  yes   ✓
 2   Attention Is All You Need      Vaswani et al.   2017   arXiv             yes   ✓
 ...
10 result(s)
```

Duplicate entries (same DOI) are merged automatically.

![Basic search demo](/gifs/01_quick_search.gif)

## Limit results per source

```bash
mosaic search "CRISPR gene editing" -n 25
```

The `-n` / `--max` flag controls how many results are requested from **each** source (default: 10).

## Open-access filter

```bash
mosaic search "quantum computing" --oa-only
```

Hides papers that have neither `is_open_access=true` nor a known PDF link.

## Search a single source

```bash
mosaic search "RNA velocity" --source epmc
mosaic search "neural ODE" --source arxiv
mosaic search "drug discovery" --source ss
```

| Shorthand | Source |
|-----------|--------|
| `arxiv`   | arXiv |
| `ss`      | Semantic Scholar |
| `sd`      | ScienceDirect |
| `doaj`    | DOAJ |
| `epmc`    | Europe PMC |
| `pubmed`  | PubMed |

## Download PDFs

```bash
mosaic search "diffusion models image generation" --oa-only --download
```

For each result that has a PDF link (or a DOI that Unpaywall can resolve), the file is saved to `~/mosaic-papers/` with the naming pattern:

```
{FirstAuthorLastName}_{Year}_{Title_slug}.pdf
```

Already-downloaded files are skipped automatically.

![Search and download demo](/gifs/02_search_download.gif)

## Download by DOI

```bash
mosaic get 10.48550/arXiv.1706.03762
```

Fetches a single paper by DOI. MOSAIC first checks the local cache, then tries Unpaywall if no PDF URL is known.

![Download by DOI demo](/gifs/04_doi_get.gif)

## Filter by year

```bash
# Exact year
mosaic search "transformer" --year 2017

# Inclusive range
mosaic search "diffusion models" -y 2020-2023

# Explicit list of years
mosaic search "BERT" -y 2019,2020,2021
```

The year filter is passed to each source's native API where supported (arXiv, Semantic Scholar, ScienceDirect, Europe PMC, DOAJ), and applied as a post-processing step on all results as a safety net.

## Filter by author

```bash
# Single author substring match
mosaic search "attention" --author Vaswani

# Multiple authors (OR logic — paper must match at least one)
mosaic search "graph neural" -a Kipf -a Velickovic
```

Author matching is case-insensitive and substring-based, so `--author Hinton` matches `"Geoffrey E. Hinton"`.

## Filter by journal

```bash
# Substring match against the journal name
mosaic search "protein structure" --journal "Nature"
mosaic search "RNA sequencing" -j "Nucleic Acids"
```

## Combining filters

Filters compose with AND logic (year AND author AND journal must all match):

```bash
# Papers by Vaswani from 2017, open-access, download PDFs
mosaic search "attention mechanism" -y 2017 -a Vaswani --oa-only --download

# Papers in Nature between 2020 and 2023, from Europe PMC
mosaic search "CRISPR" -j Nature -y 2020-2023 --source epmc -n 25

# Broad search, open-access only, download everything, from arXiv
mosaic search "large language model" -n 50 --source arxiv --oa-only --download
```

![Multi-filter search demo](/gifs/03_filter_search.gif)

## Verbose mode

Add `--verbose` to any search to see a per-source breakdown and deduplication report printed before the results table:

```bash
mosaic search "transformer attention" --verbose
```

```
╭─ Search stats ────────────────────────────────────────────────╮
│ Sources    arXiv, Semantic Scholar, OpenAlex, Crossref        │
│ Raw        arXiv=12  Semantic Scholar=18  OpenAlex=15  …  → 54 total │
│ Unique     31 papers  (23 merged by DOI)                      │
│ Filters    none                                               │
╰───────────────────────────────────────────────────────────────╯
```

Useful for tuning source selection and understanding which sources contribute unique results.

## Sort results

Use `--sort` to rank results after the search:

```bash
# Most-cited papers first (citation count from Semantic Scholar and OpenAlex)
mosaic search "transformer attention" --sort citations

# Newest papers first
mosaic search "diffusion models" --sort year

# Combine with other flags
mosaic search "protein folding" --oa-only --sort citations -n 20
```

When `--sort citations` is active, the results table gains a **Cited** column showing the citation count for each paper. Papers from sources that do not return citation data (arXiv, DOAJ, …) show `–` and are placed after all papers with known counts.

## Find similar papers

`mosaic similar` discovers related literature from any DOI or arXiv ID — no search query needed.

```bash
mosaic similar 10.48550/arXiv.1706.03762
```

```
Similar to: Attention Is All You Need

 #   Title                                       Authors           Year   Source     OA    PDF
 1   BERT: Pre-training of Deep Bidirectional…   Devlin et al.     2019   OpenAlex   yes   ✓
 2   Language Models are Few-Shot Learners       Brown et al.      2020   OpenAlex   no    –
...
```

```bash
# arXiv prefix, sort by citations, open-access only
mosaic similar arxiv:1706.03762 -n 20 --sort citations --oa-only

# Save to BibTeX for Zotero / LaTeX
mosaic similar 10.48550/arXiv.1706.03762 --output related.bib
```

Two sources contribute results:

- **OpenAlex** `related_works` — always queried, no key required
- **Semantic Scholar** recommendations — used when `ss-key` is set in config (dramatically increases recall)

See the [Find Similar Papers guide](./similar) for the full reference, identifier formats, and workflow tips.
