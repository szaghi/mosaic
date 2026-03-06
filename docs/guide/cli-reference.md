---
title: CLI Reference
---

# CLI Reference

```
mosaic [OPTIONS] COMMAND [ARGS]...
```

## Global options

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | `-v` | Print the installed version and exit |
| `--help` | | Show help and exit |

```bash
mosaic --version   # e.g. mosaic 0.0.5
mosaic -v
```

## Commands

### `search`

Search for papers across all configured sources.

```
mosaic search [OPTIONS] QUERY
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--max` | `-n` | int | `10` | Max results per source |
| `--download` | `-d` | flag | off | Download available PDFs after search |
| `--oa-only` | | flag | off | Show only open-access papers |
| `--pdf-only` | | flag | off | Show only papers with a known PDF URL |
| `--source` | `-s` | str | all | Limit to one source |
| `--year` | `-y` | str | | Year filter (see formats below) |
| `--author` | `-a` | str | | Author filter, repeatable |
| `--journal` | `-j` | str | | Journal name substring filter |
| `--field` | `-f` | str | `all` | Scope query to `title`, `abstract`, or `all` |
| `--raw-query` | | str | | Raw query sent directly to APIs, bypasses all transforms |

**Source shorthands for `--source`:**

| Shorthand | Source |
|-----------|--------|
| `arxiv` | arXiv |
| `ss` | Semantic Scholar |
| `sd` | ScienceDirect |
| `doaj` | DOAJ |
| `epmc` | Europe PMC |
| `oa` | OpenAlex |
| `base` | BASE |
| `core` | CORE |

**`--year` / `-y` formats:**

| Format | Example | Meaning |
|--------|---------|---------|
| Single year | `2020` | Exact year |
| Range | `2018-2022` | Inclusive range |
| List | `2019,2021,2023` | Specific years only |

**`--author` / `-a` behaviour:**
- Case-insensitive substring match against any author name in the paper
- Repeat the flag for multiple authors — paper must match **at least one**
- Example: `-a Hinton -a LeCun` returns papers authored by either

**`--journal` / `-j` behaviour:**
- Case-insensitive substring match against the journal name
- Example: `-j "Nature"` matches *Nature*, *Nature Communications*, *Nature Methods*, etc.

**Filter application:**

Each filter is applied at the **source API level** where supported, then as a **post-processing step** on all returned results:

| Source | Year | Author | Journal |
|--------|:----:|:------:|:-------:|
| arXiv | ✓ native | ✓ native | ✓ native |
| Semantic Scholar | ✓ native | post-process | post-process |
| ScienceDirect | ✓ native | ✓ native | ✓ native |
| Europe PMC | ✓ native | ✓ native | ✓ native |
| DOAJ | ✓ native | ✓ native | ✓ native |
| OpenAlex | ✓ native | post-process | post-process |
| BASE | ✓ native | ✓ native | ✓ native |
| CORE | ✓ native | ✓ native | ✓ native |

**`--field` / `-f` behaviour:**
- `all` (default): query is sent as a general full-text search to each source
- `title`: scopes the query to the title field using each source's native syntax
- `abstract`: scopes the query to the abstract field using each source's native syntax

**`--raw-query` behaviour:**
- Sent verbatim to every queried source, bypassing all field/author/journal transforms
- Useful for power-users who know each source's query language (e.g. arXiv's `ti:` prefixes, Lucene syntax for BASE/DOAJ/CORE)
- Note: year filter (`-y`) is still applied as post-processing even when `--raw-query` is set

**Examples:**

```bash
# Search all sources
mosaic search "protein folding"

# 25 results per source, open-access only
mosaic search "deep learning" -n 25 --oa-only

# Filter by year range
mosaic search "diffusion models" -y 2020-2023

# Filter by exact year and author
mosaic search "attention" -y 2017 -a Vaswani

# Filter by journal (substring)
mosaic search "CRISPR" -j "Nature" -y 2021-2023

# Multiple authors (OR), single source, download
mosaic search "graph neural" -a Kipf -a Velickovic --source ss --download

# Search arXiv only, download PDFs
mosaic search "diffusion models" --source arxiv --download

# Scope query to title only
mosaic search "attention mechanism" --field title

# Scope query to abstract only (shorter synonym)
mosaic search "CRISPR off-target" -f abstract --source epmc -n 50

# Power-user raw query (arXiv native syntax)
mosaic search "" --raw-query "ti:transformers AND au:Vaswani" --source arxiv
```

---

### `get`

Download a paper by DOI. Uses Unpaywall as fallback if no PDF URL is known.

```
mosaic get [OPTIONS] DOI
```

**Examples:**

```bash
mosaic get 10.48550/arXiv.1706.03762
mosaic get 10.1038/s41586-021-03819-2
```

---

### `config`

View or update MOSAIC configuration.

```
mosaic config [OPTIONS]
```

| Option | Type | Description |
|--------|------|-------------|
| `--show` | flag | Print current config as JSON |
| `--elsevier-key TEXT` | str | Set Elsevier/ScienceDirect API key |
| `--ss-key TEXT` | str | Set Semantic Scholar API key |
| `--unpaywall-email TEXT` | str | Set Unpaywall email |
| `--download-dir TEXT` | str | Set PDF download directory |

**Examples:**

```bash
# Show current config
mosaic config --show

# Set multiple values at once
mosaic config --unpaywall-email me@uni.edu --download-dir ~/papers

# Enable ScienceDirect
mosaic config --elsevier-key abc123def456
```

---

### `notebook create`

Create a Google NotebookLM notebook from a search query or a directory of PDFs.

```
mosaic notebook create [OPTIONS] NAME
```

Requires the `[notebooklm]` extra — see [NotebookLM Integration](./notebooklm).

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--query` | `-q` | str | | Search query to populate the notebook |
| `--from-dir` | | path | | Import all PDFs from this directory |
| `--max` | `-n` | int | `10` | Max results per source (with `--query`) |
| `--oa-only` | | flag | off | Only include open-access papers |
| `--pdf-only` | | flag | off | Only include papers with a known PDF URL |
| `--podcast` | | flag | off | Queue an Audio Overview after import |
| `--year` | `-y` | str | | Year filter (same formats as `search`) |
| `--author` | `-a` | str | | Author filter, repeatable |
| `--journal` | `-j` | str | | Journal name substring filter |
| `--field` | `-f` | str | `all` | Scope query to `title`, `abstract`, or `all` |
| `--raw-query` | | str | | Raw query sent directly to APIs, bypasses all transforms |

`--query` and `--from-dir` are mutually exclusive; exactly one must be provided. Filters (`-y`, `-a`, `-j`, `-f`, `--raw-query`) only apply when using `--query`. `--oa-only` and `--pdf-only` apply in both modes.

**Examples:**

```bash
# Search, download, and import into a new notebook
mosaic notebook create "Transformers" --query "attention is all you need" --oa-only

# Filter by year and queue an Audio Overview
mosaic notebook create "AMR-GPU" --query "adaptive mesh refinement gpu" -y 2024-2026 --oa-only --podcast

# Filter by author and journal
mosaic notebook create "Hinton Papers" --query "deep learning" -a Hinton -j "Nature" --oa-only

# Import PDFs you already have locally
mosaic notebook create "My Papers" --from-dir ~/mosaic-papers/
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Invalid argument or unknown source |
