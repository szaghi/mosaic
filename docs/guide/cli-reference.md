---
title: CLI Reference
---

# CLI Reference

```
mosaic [OPTIONS] COMMAND [ARGS]...
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
| `--source` | `-s` | str | all | Limit to one source |
| `--year` | `-y` | str | | Year filter (see formats below) |
| `--author` | `-a` | str | | Author filter, repeatable |
| `--journal` | `-j` | str | | Journal name substring filter |

**Source shorthands for `--source`:**

| Shorthand | Source |
|-----------|--------|
| `arxiv` | arXiv |
| `ss` | Semantic Scholar |
| `sd` | ScienceDirect |
| `doaj` | DOAJ |
| `epmc` | Europe PMC |

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

# Free text + specific source
mosaic search "CRISPR off-target" --source epmc -n 50
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

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Invalid argument or unknown source |
