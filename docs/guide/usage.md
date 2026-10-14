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
| `pmc`     | PubMed Central |
| `rxiv`    | bioRxiv / medRxiv |

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

MOSAIC checks the local cache first. If the paper was seen in a previous search and a PDF URL is already known, the download starts immediately — no Unpaywall round-trip. Otherwise it falls back to Unpaywall, then a saved browser session.

![Download by DOI demo](/gifs/04_doi_get.gif)

## Bulk download from BibTeX or CSV

```bash
# Download all DOIs found in a BibTeX export (Zotero, JabRef, Mendeley…)
mosaic get --from refs.bib

# Download from a CSV with a 'doi' column
mosaic get --from references.csv

# Mark unresolvable papers as skipped instead of failed
mosaic get --from refs.bib --oa-only

# Save to a custom directory
mosaic get --from refs.bib --download-dir ~/papers
```

MOSAIC extracts every `doi = {…}` field from `.bib` files (no extra dependency) or reads the `doi` column from `.csv` files, and deduplicates. Each DOI's title, authors and year are looked up on Crossref (cached papers skip the lookup), so files are named as in a normal search rather than after the bare DOI. It then prints a per-entry result followed by a summary:

```
Found 42 DOI(s) in refs.bib
  ✓ 2017_arXiv_Vaswani_Attention_Is_All_You_Need.pdf
  ✓ 2019_Semantic_Scholar_Devlin_BERT.pdf
  – 10.1016/j.celrep.2020.107834 (no OA copy)
  …

Done: 35 downloaded, 4 failed, 3 skipped (no OA copy)
```

![Bulk download from BibTeX demo](/gifs/12_bulk_get.gif)

## File PDFs you downloaded yourself

`mosaic import` moves PDFs you already have into the library, named and recorded exactly as if `mosaic get` had downloaded them:

```bash
mosaic import ~/Downloads/1-s2.0-S0376042106000029-main.pdf
mosaic import ~/Downloads/*.pdf --download-dir ~/papers/project
mosaic import scan.pdf --doi 10.1016/j.paerosci.2006.01.001
```

```
  ✓ 1-s2.0-S0376042106000029-main.pdf → ~/papers/project/2005_Crossref_Progress_in_Aerospace_Sciences_Boyd_Numerical_modeling_of_….pdf
    Numerical modeling of spacecraft electric propulsion thrusters (2005) — DOI 10.1016/j.paerosci.2006.01.001, found via filename
```

The DOI is detected automatically, in this order:

1. the document's own DOI in the PDF metadata;
2. the article ID in a ScienceDirect download name (`1-s2.0-<PII>-main.pdf`), looked up on Crossref;
3. a DOI in the content, but only if exactly one appears (a reference list names many, so several means "unknown").

If none applies, MOSAIC asks for `--doi`. Title, authors and year come from the cache or Crossref. Files that are not PDFs are rejected and left alone. An existing PDF with the same name is not overwritten without `--force`; an HTML page saved by versions before 1.6 is replaced. The paper is recorded in the cache, so `mosaic cache verify` and `mosaic index` see it.

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

## Cache-first search

Pass `--prefer-cache` to substitute rich cached records for freshly fetched ones:

```bash
mosaic search "transformer attention" --prefer-cache
```

When a fetched paper has a matching UID already in the local cache **and** that record is considered *rich* (has abstract + year + at least one author), MOSAIC uses the cached version instead of the freshly fetched one. This avoids redundant Unpaywall lookups and preserves metadata accumulated across earlier runs.

Combine with any other flags:

```bash
# Cache-enriched records, open-access only, sorted by citations
mosaic search "protein folding" --prefer-cache --oa-only --sort citations
```

See [Cache Management](./cache) for how records are enriched when the same paper arrives from multiple sources.

## Offline / cached search

Use `--cached` to search only the papers already stored in the local cache — no network requests, no API keys needed, instant results:

```bash
mosaic search "attention mechanism" --cached
```

All the usual filters, sort, and export options still apply:

```bash
# Filter cached papers by year and author, open-access only
mosaic search "CRISPR" --cached -y 2020-2024 -a Zhang --oa-only

# Sort cached results by citation count and export to BibTeX
mosaic search "diffusion models" --cached --sort citations --output refs.bib
```

The cache is populated automatically by every regular `search`, `similar`, and `get` run — so the more you use MOSAIC, the richer your local library becomes.

### Relevance-ranking your local library

Combine `--cached` with `--sort relevance` to re-rank your collected bibliography
against any query — with no network access and no API keys required:

```bash
mosaic search "transformer attention" --cached --sort relevance
```

This is the fastest way to sift a bibliography you have already built.  To load
a `.bib` or `.csv` file into the cache first:

```bash
mosaic get --from refs.bib            # populate cache from a BibTeX export
mosaic search "your query" --cached --sort relevance   # then rank offline
```

To rank every paper in the cache (not pre-filtered by keyword), pass an empty query:

```bash
mosaic search "" --cached --sort relevance
```

See the [Relevance Ranking guide](./relevance-ranking#ranking-your-local-library)
for the full reference including filters, export, and LLM setup.

![Offline cached search demo](/gifs/14_cached_search.gif)

## Warnings

By default MOSAIC suppresses per-source warnings (rate-limits, timeouts, 5xx errors) to keep the output clean. Pass `--verbose` as a **global flag** (before the subcommand) to reveal them:

```bash
mosaic --verbose search "transformer attention"
```

```
Warning: Semantic Scholar: rate limited (HTTP 429); retry in ~60s
Warning: DBLP: HTTP 500 from dblp.org
```

Short rate-limit waits are retried automatically before a warning is shown; see [Sources → Rate limits and quotas](./sources#rate-limits-and-quotas).

Useful when debugging connectivity or API key issues.

## AI summary of results

`--summarise` (or `--summarize`) adds a one-paragraph synthesis of the results below the table. It covers the main themes and methods and how they evolved, citing papers by their row number:

```bash
mosaic search "large eddy simulation wall model" --source arxiv --max 6 --summarise
```

```
╭─ AI summary ──────────────────────────────────────────────────────────────╮
│ The central thread across these papers is function enrichment within      │
│ high-order discontinuous Galerkin schemes for coarse-mesh wall modeling.  │
│ Initially proposed for incompressible LES [6], the approach was extended  │
│ to RANS [5], hybrid RANS/LES [4], and detached-eddy simulation [1] ...    │
╰───────────────────────────────────────────────────────────────────────────╯
```

- It uses the LLM configured for [RAG](./rag) and [relevance ranking](./relevance-ranking): OpenAI, Anthropic, or any OpenAI-compatible local server (Ollama, LM Studio, ...). Set it with `mosaic config --llm-provider ... --llm-api-key ... --llm-model ...`.
- Only titles and abstracts are sent, at most the first 40 results and 1 000 characters per abstract. The model is told to use nothing else, but check any claim that matters against the paper itself.
- No index is needed, unlike [`mosaic ask`](./rag), which answers questions over your indexed library.
- It works with `--cached` and `--semantic` too. With `--json`, the paragraph is returned in a `summary` field, and `[n]` refers to the n-th entry of `papers`.
- If no LLM is configured, the LLM call fails, or no result has an abstract, the results are still shown and a one-line note explains why there is no summary.

## Search stats

Add `--stats` to a `search` command to print a per-source breakdown and deduplication report after the search completes:

```bash
mosaic search "transformer attention" --stats
```

```
        Search stats
  Source               Results
  ───────────────────────────
  arXiv                     12
  Semantic Scholar          18
  OpenAlex                  15
  Crossref                   9
  ───────────────────────────
  Total raw                 54
  Merged                    23
  Unique                    31
```

Useful for tuning source selection and understanding which sources contribute unique results. Both flags can be combined:

```bash
mosaic --verbose search "protein folding" --stats
```

## Sort results

Use `--sort` to rank results after the search:

```bash
# Most-cited papers first (citation count from Semantic Scholar and OpenAlex)
mosaic search "transformer attention" --sort citations

# Newest papers first
mosaic search "diffusion models" --sort year

# Most relevant to the query first (BM25 or LLM scoring)
mosaic search "transformer attention" --sort relevance

# Combine with other flags
mosaic search "protein folding" --oa-only --sort citations -n 20
```

When `--sort citations` is active, the results table gains a **Cited** column showing the citation count for each paper. Papers from sources that do not return citation data (arXiv, DOAJ, …) show `–` and are placed after all papers with known counts.

When `--sort relevance` is active, the results table gains a **Rel.** column (0.00 – 1.00) showing each paper's normalised relevance score. The highest-scoring paper always shows 1.00.

Relevance scoring uses **BM25** by default (fast, local, no setup) and upgrades to an **LLM** when one is configured — enabling semantic understanding, synonym matching, and conceptual relevance that keyword overlap alone cannot capture.

See the [Relevance Ranking guide](./relevance-ranking) for setup instructions, local LLM options (Ollama, LM Studio, llama.cpp), and configuration details.

## Save results to a file

Use `--output` / `-o` to write results to disk in any of five formats.  The
format is inferred from the file extension:

```bash
mosaic search "transformer attention" --output results.csv
mosaic search "diffusion models" -y 2022-2024 --oa-only --output refs.bib
mosaic search "CRISPR" --output papers.json
mosaic search "protein folding" --output summary.md
mosaic search "RNA velocity" --output report.markdown
mosaic search "CRISPR" --output refs.ris
```

### Supported formats

| Extension | Format | Best for |
|-----------|--------|----------|
| `.csv` | CSV table | Excel, Google Sheets, data analysis |
| `.json` | JSON array | Scripting, pipelines, custom tooling |
| `.bib` | BibTeX | LaTeX, Zotero, JabRef, Mendeley |
| `.ris` | RIS | EndNote, Mendeley, Papers, RefWorks, any reference manager |
| `.md` | Markdown table | Quick README or wiki table |
| `.markdown` | Markdown sections | Detailed per-paper notes, static-site generators |

### Format details

**`.csv`** — 14 columns: `title`, `authors` (semicolon-separated), `year`, `doi`,
`arxiv_id`, `journal`, `volume`, `issue`, `pages`, `source`, `is_open_access`,
`citation_count`, `pdf_url`, `url`.

**`.json`** — JSON array of objects; `authors` is a native JSON array; `null` for
missing fields; pretty-printed with 2-space indentation.

**`.ris`** — standard RIS format accepted by virtually every reference manager
(EndNote, Mendeley, Papers, RefWorks, Zotero, JabRef). Entry type `JOUR` for
journal papers, `GEN` for preprints. One `AU` line per author; pages split
into `SP`/`EP`; `UR` set from `url`, falling back to `pdf_url`.

**`.bib`** — `@article` for papers with a journal, `@misc` for preprints.
Auto-generated cite key: `LastName + Year + FirstTitleWord`
(e.g. `Vaswani2017Attention`). ArXiv papers get `eprint` and `eprinttype=arXiv`
fields. Open-access papers get `note={Open Access}`.

**`.md`** — a single compact Markdown table (columns: #, Title, Authors, Year,
DOI, Source, OA, PDF).

**`.markdown`** — one `## Title` section per paper, each containing a key/value
table of all available fields (abstract included); empty fields are omitted.

### Export multiple formats in one command

`--output` is **repeatable** — pass it more than once to write several files
simultaneously without re-running the search:

```bash
# Write BibTeX, CSV, and a Markdown summary in one go
mosaic search "large language models" -n 30 --oa-only \
  --output refs.bib \
  --output results.csv \
  --output summary.md
```

### Combine with other flags

```bash
# Open-access papers from 2020–2024, sorted by citations, saved as BibTeX
mosaic search "diffusion models" -y 2020-2024 --oa-only --sort citations \
  --output diffusion.bib

# Single-source search saved as JSON for scripting
mosaic search "RNA splicing" --source epmc -n 50 --output splicing.json

# Author filter + journal filter, saved as detailed Markdown notes
mosaic search "graph neural" -a Kipf -j "ICLR" --output gnns.markdown
```

### Works with `mosaic similar` too

`--output` is available on the `similar` command with the same formats:

```bash
# Find related papers and export to BibTeX for LaTeX
mosaic similar 10.48550/arXiv.1706.03762 --output related.bib

# Export to multiple formats at once
mosaic similar arxiv:1706.03762 -n 30 --sort citations \
  --output related.bib \
  --output related.json
```

## Export to Zotero

Push results directly into your Zotero library — no copy-paste required.

```bash
# Local API (Zotero must be running)
mosaic search "CRISPR" --oa-only --zotero

# Push to a named collection
mosaic search "transformers" --zotero --zotero-collection "Deep Learning"

# Download PDFs and link them in Zotero
mosaic search "diffusion models" --download --zotero --zotero-collection "Generative AI"
```

For the **web API** (Zotero not running locally), configure once:
```bash
mosaic config --zotero-key YOUR_API_KEY
```
Then use `--zotero` as normal — MOSAIC will talk to `api.zotero.org`.

![Zotero integration demo](/gifs/09_zotero.gif)

See the [Zotero Integration guide](./zotero) for the full setup and all options.

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

![Find similar papers demo](/gifs/10_similar.gif)
