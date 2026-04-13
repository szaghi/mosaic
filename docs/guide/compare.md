---
title: Compare Papers
---

# Compare Papers (`mosaic compare`)

`mosaic compare` generates a structured comparison table across a set of cached papers.  When an LLM is configured, it extracts researcher-defined dimensions (method, dataset, metric, result by default) from each paper's title and abstract.  Without an LLM, only metadata fields (year, source, journal, DOI) are populated.

## Quickstart

```bash
# Compare top-cited cached papers on diffusion models (LLM required for method/dataset/metric/result)
mosaic compare --query "diffusion models" --sort citations -n 15

# Save to Markdown
mosaic compare --query "transformer attention" --output comparison.md

# Compare papers from a BibTeX file along custom axes
mosaic compare --from refs.bib --dimensions "method,dataset,BLEU,limitations"

# Export as CSV or JSON
mosaic compare --query "protein folding" --output comparison.csv
mosaic compare --query "protein folding" --output comparison.json
```

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--query TEXT` | `-q` | | Filter papers from the cache by title/abstract |
| `--from FILE` | | | Load papers from a `.bib` or `.csv` file |
| `--max INT` | `-n` | `20` | Maximum number of papers to compare |
| `--dimensions TEXT` | | `method,dataset,metric,result` | Comma-separated comparison axes |
| `--output FILE` | `-o` | | Write table to file (`.md`, `.csv`, `.json`) |
| `--sort TEXT` | | | Pre-sort papers: `citations` (most cited first) or `year` (newest first) |

## How it works

### Paper selection

Papers are taken from the local cache in three ways:

1. **`--query`** — full-text search on title and abstract.
2. **`--from FILE`** — DOIs extracted from a `.bib` or `.csv` file, then looked up in the cache.
3. **No filter** — all cached papers, up to `--max`.

After filtering, papers are optionally sorted by citation count or year and truncated to `--max`.

### LLM extraction

When `[llm] api_key` and `[llm] provider` are set in the config, MOSAIC sends batches of 20 papers to the LLM with a structured prompt:

```
For each paper below extract the following dimensions: "method", "dataset", "metric", "result".
Return a JSON array of exactly N objects. Each object must have exactly these keys: …
Use "-" when a dimension cannot be inferred from the title or abstract.
```

The LLM fills in each field from the title and abstract (up to 300 characters).  Unavailable fields are marked `–`.

::: tip Configure LLM
```bash
mosaic config --llm-provider openai --llm-api-key sk-...
# or Anthropic:
mosaic config --llm-provider anthropic --llm-api-key sk-ant-...
```
:::

### Metadata-only fallback

Without an LLM, or when the LLM call fails, MOSAIC falls back to extracting fields that are directly available in the cache:

| Dimension name | Extracted from |
|----------------|---------------|
| `year` | `paper.year` |
| `source` | `paper.source` |
| `journal` | `paper.journal` |
| `doi` | `paper.doi` |
| `authors` | `paper.short_authors` |
| `citations` / `citation_count` / `cited` | `paper.citation_count` |
| anything else | `–` |

### Output formats

| Extension | Format |
|-----------|--------|
| terminal (default) | Rich table |
| `.md` / `.markdown` | Markdown table |
| `.csv` | CSV with header row |
| `.json` | JSON array, one object per paper |

The terminal table is always printed; `--output` saves a copy to disk in addition.

## Examples

### Terminal output

```
mosaic compare --query "diffusion models" --sort citations -n 5
```

```
 #  Title                          Year  Authors          Method              Dataset      Metric  Result
 1  DDPM                           2020  Ho et al.        Denoising diffusion  CIFAR-10    FID     3.17
 2  Stable Diffusion               2022  Rombach et al.   Latent diffusion     LAION-5B    FID     12.6
 3  DALL-E 2                       2022  Ramesh et al.    Hierarchical GLIDE   COCO        FID     10.39
…
```

### Markdown table

```markdown
| # | Title | Year | Authors | Method | Dataset | Metric | Result |
|---|-------|------|---------|--------|---------|--------|--------|
| 1 | DDPM  | 2020 | Ho et al. | Denoising diffusion | CIFAR-10 | FID | 3.17 |
```

### Custom dimensions

```bash
mosaic compare --from refs.bib --dimensions "task,architecture,training_data,main_limitation"
```

Any dimension name works; the LLM will attempt to extract it from the abstract.

## Limitations

- Accuracy depends on what is stated in the abstract.  Full-text extraction is not yet supported.
- Batching is limited to 20 papers per LLM call; larger sets take proportionally longer.
- Very long tables (>50 rows) can be hard to read in the terminal — use `--output` to save as Markdown or CSV.

## Workflow example

```bash
# Step 1: collect papers
mosaic search "graph neural networks" -n 50

# Step 2: compare top-cited methods
mosaic compare --query "graph neural networks" --sort citations -n 20 \
               --dimensions "task,gnn_type,dataset,accuracy" \
               --output gnn-comparison.md

# Step 3: visualise the citation network of the same corpus
mosaic network --query "graph neural networks" --cluster --output gnn-network.md
```
