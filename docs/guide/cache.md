---
title: Cache Management
---

# Cache Management

Every `search`, `similar`, and `get` run automatically saves results to a local SQLite database (`~/.local/share/mosaic/cache.db`). Over time this cache becomes a rich, queryable library of papers you have already discovered.

The `mosaic cache` subcommand lets you inspect, search, and maintain that library — with no network requests needed.

## Quick overview

```bash
mosaic cache stats          # summary of what's stored
mosaic cache list           # browse cached papers
mosaic cache show <id>      # full record for one paper
mosaic cache verify         # check which PDF files still exist on disk
mosaic cache clean          # remove stale download records
mosaic cache clear          # wipe the whole cache
mosaic cache export out.csv # bulk export to file
```

![Cache management demo](/gifs/11_cache.gif)

## stats

Print a summary of the cache contents:

```bash
mosaic cache stats
```

```
Cache stats
  Papers          312
  With abstract   278
  With PDF URL     94
  Open access     201
  Downloaded       47
  Searches        128
  Exports          12
  DB size         1.2 MB
```

## list

Browse papers stored in the cache, newest-first:

```bash
mosaic cache list
mosaic cache list --limit 20
mosaic cache list --limit 20 --offset 40   # page 3 of 20
mosaic cache list --query "attention"      # substring filter on title / abstract
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--limit` | `-n` | `20` | Max papers to show |
| `--offset` | | `0` | Skip this many rows (for pagination) |
| `--query` | `-q` | | Substring filter on title and abstract |

Output format:

```
 #   Title                              Authors          Year   Source            OA    PDF   Downloaded
 1   Attention Is All You Need          Vaswani et al.   2017   Semantic Scholar  yes   ✓     ✓
 2   BERT: Pre-training…                Devlin et al.    2019   arXiv             yes   ✓     –
...
20 of 312 paper(s)
```

## show

Show the full cached record for a single paper identified by DOI or arXiv ID:

```bash
mosaic cache show 10.48550/arXiv.1706.03762
mosaic cache show arxiv:1706.03762
```

```
Title        Attention Is All You Need
Authors      Vaswani, Ashish; Shazeer, Noam; ...
Year         2017
DOI          10.48550/arxiv.1706.03762
arXiv ID     1706.03762
Journal      –
Source       arXiv
Open access  yes
PDF URL      https://arxiv.org/pdf/1706.03762
Citations    95 847
Abstract     The dominant sequence transduction models...

Download
  Path       ~/mosaic-papers/2017_arXiv_Vaswani_Attention_Is_All_You_Need.pdf
  Status     ok
```

## verify

Check whether each tracked PDF file still exists on disk:

```bash
mosaic cache verify
```

```
  ✓  ~/mosaic-papers/2017_arXiv_Vaswani_Attention_Is_All_You_Need.pdf
  ✗  ~/mosaic-papers/2019_arXiv_Devlin_BERT.pdf  [missing]
  ...
2 of 47 files are missing.
```

## clean

Remove download records whose files no longer exist on disk:

```bash
mosaic cache clean
```

```
Removed 2 stale download record(s).
```

Only records with `status=ok` are checked — records with `status=failed` are left untouched. The paper metadata itself is never deleted; only the download tracking entry is removed.

## clear

Wipe **all** papers, downloads, searches, and exports from the cache:

```bash
mosaic cache clear          # asks for confirmation
mosaic cache clear --yes    # skip the confirmation prompt
```

This is irreversible. PDF files already saved to disk are not deleted.

## export

Bulk-export cached papers to a file. The format is inferred from the file extension:

```bash
mosaic cache export results.csv
mosaic cache export refs.bib
mosaic cache export refs.ris
mosaic cache export papers.json
mosaic cache export summary.md
mosaic cache export report.markdown
```

| Extension | Format |
|-----------|--------|
| `.csv` | CSV table |
| `.json` | JSON array |
| `.bib` | BibTeX |
| `.ris` | RIS (EndNote, Mendeley, RefWorks, Papers, …) |
| `.md` | Markdown table |
| `.markdown` | Markdown sections (one `##` per paper) |

Export all papers at once, or filter first with `--query`:

```bash
mosaic cache export --query "diffusion" diffusion.bib
```

## Smart enrichment

When the same paper arrives from multiple sources, MOSAIC merges the records using field-level rules rather than blindly overwriting:

| Field | Rule |
|-------|------|
| `abstract` | Keep the longer version |
| `pdf_url` | Preserve the first non-null value (never overwrite) |
| `is_open_access` | `True` supersedes `False` |
| `citation_count` | Keep the higher value; `null` treated as unknown |
| `authors` | Keep the longer list |
| `doi`, `arxiv_id`, `journal`, `volume`, `issue`, `pages`, `url` | Fill if empty, never overwrite |
| `title`, `year`, `source` | Always keep the first-recorded value |

This means every subsequent search enriches the existing records rather than degrading them.

## Cache-first search (--prefer-cache)

Pass `--prefer-cache` to a regular `search` to substitute rich cached records for freshly fetched ones:

```bash
mosaic search "transformer attention" --prefer-cache
```

When a fetched paper has a matching UID in the cache **and** the cached record is considered *rich* (has abstract + year + at least one author), MOSAIC uses the cached version instead of the freshly fetched one. This avoids redundant Unpaywall round-trips and preserves enriched metadata accumulated across earlier searches.

A record is *rich* when it has:
- A non-empty abstract
- A known publication year
- At least one author

`--prefer-cache` can be combined with all other `search` flags:

```bash
# Use cache-enriched records, open-access only, sorted by citations
mosaic search "protein folding" --prefer-cache --oa-only --sort citations
```

## Offline search

### Keyword search — `--cached`

Use `--cached` to search *only* the local cache — no network requests, no API keys needed, instant results:

```bash
mosaic search "attention mechanism" --cached
mosaic search "protein folding" --cached --sort citations --oa-only
```

All the usual filters, sort, and export options still apply. See [Usage → Offline / cached search](./usage#offline-cached-search) for details.

![Offline cached search demo](/gifs/14_cached_search.gif)

### Semantic search — `--semantic`

`--semantic` goes beyond keyword matching: it embeds the query with the same model used by
`mosaic index` and retrieves the most similar papers from the vector index. Synonyms,
paraphrases, and conceptual relationships are handled — even if the exact keywords are absent.

```bash
# Retrieve by meaning, not keyword overlap
mosaic search "methods that learn without labels" --semantic

# Only papers you have downloaded
mosaic search "attention mechanism" --semantic --downloaded-only
```

The results table shows a **Sim.** column (0 – 1) showing the cosine-like similarity score.

**Prerequisites:** `sqlite-vec` installed and `mosaic index` run at least once. See the [RAG guide](./rag) for setup.

### `--downloaded-only`

Both `--cached` and `--semantic` accept `--downloaded-only` to restrict results to papers for
which a PDF is stored locally:

```bash
mosaic search "graph neural network" --cached --downloaded-only
mosaic search "diffusion model" --semantic --downloaded-only
```
