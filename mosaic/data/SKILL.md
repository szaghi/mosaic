---
name: mosaic
description: >
  Expert knowledge of MOSAIC (Multi-source Scientific Article Indexer and Collector) — a CLI tool
  for searching, downloading, and managing scientific papers from 21 sources with a single command.
  Use this skill whenever the user asks about: building a bibliography programmatically, searching
  for papers across multiple sources, downloading OA PDFs, exporting to BibTeX/Zotero/Obsidian,
  interpreting mosaic --json output in AI agent or CI workflows, RAG over a paper library, finding
  similar papers, analysing citation networks, comparing papers across structured dimensions, or any
  task that involves mosaic search/get/similar/ask/chat/index/network/compare/skill commands.
  When in doubt, trigger this skill — it is better to consult it unnecessarily than to miss it.
---

# MOSAIC Expert Knowledge

MOSAIC fans out paper searches across 21 scientific sources, deduplicates results by DOI, caches
them in a local SQLite database, and can download OA PDFs. It provides structured JSON output for
AI agent and CI workflows.

## CLI Commands

```bash
mosaic search "query"           # search all enabled sources
mosaic get <doi>                # fetch metadata + download PDF by DOI
mosaic similar <doi|arxiv_id>   # find related papers via OpenAlex + Semantic Scholar
mosaic network                  # explore citation network, identify hubs and clusters
mosaic compare                  # structured comparison table across cached papers (LLM or metadata)
mosaic index                    # build/update vector index for RAG
mosaic ask "question"           # RAG Q&A over cached papers
mosaic chat                     # interactive multi-turn RAG session
mosaic config --show            # view or edit configuration
mosaic cache list               # inspect local SQLite cache
mosaic cache stats              # cache statistics
mosaic notebook create "topic"  # create a Google NotebookLM notebook
mosaic auth login elsevier      # browser session for authenticated PDF access
mosaic skill install            # install this Claude Code skill to the current project
mosaic skill install --global   # install to ~/.claude/skills/ (available in all projects)
mosaic skill show               # print skill content to stdout
```

---

## JSON Output (scripting / AI agents)

Add `--json` to `search` or `similar` for machine-readable stdout. All rich table output is
suppressed; results are written to stdout as a single JSON object. Papers are still saved to the
local cache so subsequent `--cached` queries work immediately.

```bash
mosaic search "attention mechanism" --max 20 --oa-only --json
mosaic similar 10.48550/arXiv.1706.03762 --max 15 --json
```

### JSON schema — search

```json
{
  "status": "ok",
  "query": "attention mechanism",
  "count": 3,
  "papers": [
    {
      "title": "Attention Is All You Need",
      "authors": ["Vaswani, Ashish", "Shazeer, Noam"],
      "year": 2017,
      "doi": "10.48550/arXiv.1706.03762",
      "arxiv_id": "1706.03762",
      "pii": null,
      "abstract": "The dominant sequence transduction models...",
      "journal": null,
      "volume": null,
      "issue": null,
      "pages": null,
      "pdf_url": "https://arxiv.org/pdf/1706.03762",
      "source": "arxiv",
      "is_open_access": true,
      "url": "https://arxiv.org/abs/1706.03762",
      "citation_count": 50000,
      "relevance_score": null,
      "uid": "10.48550/arxiv.1706.03762"
    }
  ],
  "errors": []
}
```

`status` is `"ok"` (errors are non-fatal warnings from individual sources, not fatal failures).
`uid` is the deduplication key used by the cache: prefers DOI → arxiv_id → pii → title slug.
Fields are always present; unavailable values are `null`.

### JSON schema — similar

Same as above but with an extra `"seed"` key:

```json
{
  "status": "ok",
  "seed": "Attention Is All You Need",
  "query": "10.48550/arXiv.1706.03762",
  "count": 10,
  "papers": [...],
  "errors": []
}
```

Exit code is 0 on success, 1 on fatal failure (bad identifier, no results).

### Agent scripting — bash

```bash
result=$(mosaic search "transformer architecture" --max 30 --oa-only --json)
count=$(echo "$result" | jq '.count')
dois=$(echo "$result" | jq -r '.papers[].doi | select(. != null)')
pdfs=$(echo "$result" | jq -r '.papers[] | select(.pdf_url != null) | .doi')
echo "Found $count papers, $(echo "$pdfs" | wc -l) with PDF"
```

### Agent scripting — Python

```python
import json, subprocess

def mosaic_json(args: list[str]) -> dict:
    r = subprocess.run(["mosaic"] + args, capture_output=True, text=True, check=False)
    if r.returncode != 0 and not r.stdout.strip():
        raise RuntimeError(f"mosaic failed: {r.stderr}")
    return json.loads(r.stdout)

# Search and parse
data = mosaic_json(["search", "FDTD high-order", "--max", "25", "--json"])
papers = data["papers"]
oa_papers = [p for p in papers if p["is_open_access"]]
print(f"Found {data['count']} papers, {len(oa_papers)} open-access")

# Find similar to the most-cited result
top = max(papers, key=lambda p: p["citation_count"] or 0)
if top["doi"]:
    related = mosaic_json(["similar", top["doi"], "--max", "10", "--json"])
```

---

## search Command

```bash
mosaic search "query" [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--max`, `-n` | 10 | Max results per source |
| `--source`, `-s` | (all) | Limit to one source shorthand (see table below) |
| `--oa-only` | off | Open-access papers only |
| `--pdf-only` | off | Papers with downloadable PDF only |
| `--year`, `-y` | — | Year filter: `"2020"`, `"2020-2024"`, or `"2020,2022,2024"` |
| `--author`, `-a` | — | Author name filter (repeatable) |
| `--journal`, `-j` | — | Journal name filter (substring match) |
| `--field`, `-f` | `all` | Scope query to `"title"`, `"abstract"`, or `"all"` |
| `--raw-query` | — | Send query directly to source API, bypass field transforms |
| `--sort` | — | Sort order: `"citations"`, `"year"`, or `"relevance"` |
| `--download`, `-d` | off | Download available PDFs after search |
| `--output`, `-o` | — | Save results to file (`.md`, `.csv`, `.json`, `.bib`, `.ris`); repeatable |
| `--cached` | off | Search only the local cache — no network requests |
| `--prefer-cache` | off | Prefer richer cached records over freshly fetched data |
| `--stats` | off | Print per-source counts and deduplication stats |
| `--zotero` | off | Export results to Zotero |
| `--zotero-collection` | — | Zotero collection name (created if missing) |
| `--obsidian` | off | Export results as notes to an Obsidian vault |
| `--json` | off | Emit structured JSON to stdout (suppresses table output) |

---

## Source Shorthands

| Shorthand | Source | Coverage | Auth |
|-----------|--------|----------|------|
| `arxiv` | arXiv | Physics, CS, Math, Biology | None |
| `ss` | Semantic Scholar | 214 M papers, all disciplines | Optional key |
| `sd` | ScienceDirect | Elsevier journals & books | API key or browser |
| `sp` | Springer (browser) | Springer, Nature (browser) | `[browser]` extra |
| `springer` | Springer API | OA Springer/Nature articles | Free API key |
| `doaj` | DOAJ | 8 M+ fully OA articles | None |
| `epmc` | Europe PMC | 45 M biomedical papers | None |
| `oa` | OpenAlex | 250 M+ works | None |
| `base` | BASE | 300 M+ from 10k+ repos | None |
| `core` | CORE | 200 M+ OA full-text | Free API key |
| `ads` | NASA ADS | Astronomy & astrophysics | Free API token |
| `ieee` | IEEE Xplore | 5 M+ IEEE papers | Free API key |
| `zenodo` | Zenodo | 3 M+ OA research outputs | None |
| `crossref` | Crossref | 150 M+ DOI registry | None |
| `dblp` | DBLP | 6 M+ CS publications | None |
| `hal` | HAL | 1.5 M+ French academic OA | None |
| `pubmed` | PubMed | 35 M+ biomedical citations | Optional key |
| `pmc` | PubMed Central | 5 M+ free full-text biomedical | Optional key |
| `rxiv` | bioRxiv/medRxiv | Life science preprints | None |
| `pedro` | PEDro | Physiotherapy evidence | Fair-use ack |
| `scopus` | Scopus | 90 M+ Elsevier citations | API key or browser |

---

## get Command

```bash
mosaic get <doi>                # single DOI — fetch metadata + download PDF
mosaic get --from refs.bib      # bulk-download from BibTeX file
mosaic get --from library.csv   # bulk-download from CSV file (must have 'doi' column)
```

Options: `--oa-only`, `--download-dir`, `--zotero`, `--zotero-collection`, `--obsidian`.

## similar Command

```bash
mosaic similar 10.48550/arXiv.1706.03762   # by DOI
mosaic similar arxiv:1706.03762             # by arXiv ID
mosaic similar <doi> --max 20 --sort citations --json
```

Uses OpenAlex `related_works` (always) and Semantic Scholar recommendations (when API key is
configured). Options are the same as `search` minus `--source` and `--year`.

---

## Export Formats

| Extension | Format |
|-----------|--------|
| `.bib` | BibTeX |
| `.ris` | RIS (Mendeley, Endnote, Reference Manager) |
| `.csv` | CSV table |
| `.json` | JSON array of paper objects |
| `.md` / `.markdown` | Markdown table |

```bash
# Save to multiple formats in one command
mosaic search "deep learning" --output refs.bib --output summary.md
```

---

## network Command

Explore the local citation graph built by `mosaic index --enrich-citations`.

```bash
mosaic network [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--query`, `-q` | — | Seed graph from cached papers matching this query (BFS subgraph) |
| `--depth` | 2 | Citation hops to follow from seed papers |
| `--min-connections` | 1 | Exclude papers with fewer edges than this |
| `--cluster` | off | Group papers into topic clusters (Louvain if `networkx` installed, else connected components) |
| `--output`, `-o` | — | Write graph to file: `.json` (D3/Gephi node-link), `.gv` (Graphviz DOT), `.md` (Mermaid) |
| `--top` | 5 | Most-connected papers to show per cluster in terminal output |

**Requires** citation edges — run `mosaic index --enrich-citations` first.
**Louvain clustering** requires `networkx`: `pipx inject mosaic-search networkx`.

```bash
# Most-connected papers in the full graph
mosaic network --top 10

# Topic subgraph with community clusters
mosaic network --query "transformer attention" --depth 2 --cluster --top 5

# Export for downstream tools
mosaic network --output graph.json   # D3.js / Gephi / NetworkX
mosaic network --output graph.gv     # Graphviz: dot -Tpng graph.gv -o graph.png
mosaic network --output graph.md     # Mermaid diagram for README / Obsidian

# Combine: topic subgraph → cluster report → save Mermaid
mosaic network --query "diffusion models" --cluster --top 5 --output diffusion.md
```

### JSON node-link schema

```json
{
  "nodes": [
    {
      "id": "doi:10.48550/arxiv.1706.03762",
      "title": "Attention Is All You Need",
      "year": 2017,
      "authors": "Vaswani et al.",
      "citation_count": 85000,
      "cluster": 0
    }
  ],
  "links": [
    { "source": "doi:10.48550/...", "target": "doi:10.18653/..." }
  ]
}
```

`cluster` is `null` when `--cluster` is not used.

---

## compare Command

Generate a structured comparison table across cached papers. With a configured LLM, extracts
dimensions from each paper's title + abstract. Without one, populates only metadata fields and
prints a notice — never fails silently.

```bash
mosaic compare [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--query`, `-q` | — | Filter papers from cache by title/abstract |
| `--from` | — | Load papers from a `.bib` or `.csv` file |
| `--max`, `-n` | 20 | Maximum number of papers to compare |
| `--dimensions` | `method,dataset,metric,result` | Comma-separated comparison axes |
| `--output`, `-o` | — | Write table to file: `.md`, `.csv`, `.json` |
| `--sort` | — | Pre-sort papers: `citations` (most cited first) or `year` (newest first) |

```bash
# Compare top-cited cached papers on a topic (LLM fills in method/dataset/metric/result)
mosaic compare --query "diffusion models" --sort citations -n 15

# Save as Markdown
mosaic compare --query "transformer attention" --output comparison.md

# Custom dimensions from a BibTeX file
mosaic compare --from refs.bib --dimensions "method,dataset,BLEU,limitations"

# Export as CSV for Excel / Google Sheets
mosaic compare --query "GNN" -n 20 --output gnn-comparison.csv

# Export as JSON for scripting
mosaic compare --query "protein folding" --output folding.json
```

**Metadata-only dimensions** (no LLM needed): `year`, `source`, `journal`, `doi`, `authors`,
`citations`. All other dimension names require an LLM and return `–` without one.

**LLM setup** (same config as RAG):

```bash
mosaic config --llm-provider openai --llm-api-key YOUR_KEY
# or Anthropic:
mosaic config --llm-provider anthropic --llm-api-key YOUR_KEY
# or local Ollama:
mosaic config --llm-provider openai --llm-base-url http://localhost:11434/v1 --llm-api-key ollama
```

---

## RAG Commands

```bash
# 1. Build/update the vector index (incremental — already-indexed papers are skipped)
mosaic index

# 2. Single-shot analysis
mosaic ask "What FDTD schemes achieve high-order accuracy in time?" --mode synthesis
mosaic ask "What open problems remain in discontinuous Galerkin methods?" --mode gaps
mosaic ask "Compare DDPM, DDIM, and score SDE" --mode compare --output report.md
mosaic ask "Extract all methods with accuracy claims" --mode extract

# 3. Interactive session
mosaic chat
```

**Modes**: `synthesis` (state of the art), `gaps` (open problems), `compare` (side-by-side
methods), `extract` (structured per-paper data extraction).

Requires `sqlite-vec` (`pipx inject mosaic-search sqlite-vec`) and a configured embedding model
+ LLM. See `mosaic config --embedding-model ...` / `--llm-provider ...`.

---

## Configuration

```bash
# View full config (TOML-formatted)
mosaic config --show

# Essential setup
mosaic config --unpaywall-email you@example.com   # enables Unpaywall PDF fallback

# API keys
mosaic config --elsevier-key YOUR_KEY             # ScienceDirect
mosaic config --ss-key YOUR_KEY                   # Semantic Scholar
mosaic config --springer-key YOUR_KEY             # Springer API
mosaic config --ads-key YOUR_KEY                  # NASA ADS
mosaic config --ieee-key YOUR_KEY                 # IEEE Xplore

# LLM (for RAG and relevance ranking)
mosaic config \
  --llm-provider openai \
  --llm-api-key YOUR_KEY \
  --llm-model gpt-4o-mini

# Ollama (local LLM — no data leaves your machine)
mosaic config \
  --embedding-model snowflake-arctic-embed2 \
  --embedding-base-url http://localhost:11434/v1 \
  --embedding-api-key ollama \
  --llm-provider openai \
  --llm-base-url http://localhost:11434/v1 \
  --llm-api-key ollama \
  --llm-model llama3.2

# Enable/disable sources
mosaic config --enable-source scopus
mosaic config --disable-source pedro

# Download location
mosaic config --download-dir ~/papers/
```

Config file: `~/.config/mosaic/config.toml`
Cache DB: `~/.local/share/mosaic/cache.db`
Default downloads: `~/mosaic-papers/`

---

## AI Agent Workflow: Building a Bibliography

```python
import json, subprocess
from pathlib import Path

def mosaic(args: list[str]) -> dict:
    r = subprocess.run(["mosaic"] + args, capture_output=True, text=True, check=False)
    if r.returncode != 0 and not r.stdout.strip():
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout)

# --- Step 1: Search multiple related queries ---
all_papers: list[dict] = []
queries = [
    "transformer self-attention",
    "BERT language model pre-training",
    "GPT autoregressive language model",
]
for q in queries:
    data = mosaic(["search", q, "--max", "15", "--oa-only", "--json"])
    all_papers.extend(data["papers"])

# --- Step 2: Deduplicate by uid (DOI / arXiv ID) ---
seen: set[str] = set()
unique: list[dict] = []
for p in all_papers:
    if p["uid"] not in seen:
        seen.add(p["uid"])
        unique.append(p)

# --- Step 3: Expand with similar papers for the top-cited seed ---
most_cited = max(unique, key=lambda p: p["citation_count"] or 0)
if most_cited.get("doi"):
    related = mosaic(["similar", most_cited["doi"], "--max", "10", "--json"])
    for p in related["papers"]:
        if p["uid"] not in seen:
            seen.add(p["uid"])
            unique.append(p)

# --- Step 4: Export the cached results to BibTeX ---
# (mosaic cache already has all papers from steps 1-3)
subprocess.run(["mosaic", "search", queries[0], "--cached", "--output", "bibliography.bib"])

# --- Step 5: Download all OA PDFs ---
for p in unique:
    if p["pdf_url"] and p.get("doi"):
        subprocess.run(["mosaic", "get", p["doi"]])

# --- Step 6: Index, enrich citations, and ask ---
subprocess.run(["mosaic", "index", "--enrich-citations"])
subprocess.run(["mosaic", "ask", "Summarise the evolution of attention mechanisms",
                "--mode", "synthesis", "--output", "synthesis.md"])

# --- Step 7: Explore the citation network ---
subprocess.run(["mosaic", "network", "--query", "attention mechanism",
                "--cluster", "--top", "5", "--output", "network.md"])

# --- Step 8: Compare methods across top-cited papers ---
subprocess.run(["mosaic", "compare", "--query", "attention mechanism",
                "--sort", "citations", "-n", "20", "--output", "comparison.md"])
```

---

## Zotero Integration

```bash
# Push search results to a Zotero collection (Zotero must be running)
mosaic search "deep learning" --max 20 --zotero --zotero-collection "Deep Learning"

# Push + download PDFs
mosaic search "protein folding" --oa-only --download --zotero --zotero-collection "Bioinformatics"

# Bulk-download an existing .bib file and send to Zotero
mosaic get --from refs.bib --zotero --zotero-collection "Imported"

# Web API (no Zotero app needed)
mosaic config --zotero-key YOUR_WEB_API_KEY
mosaic search "FDTD" --zotero
```

## Obsidian Integration

```bash
mosaic config --obsidian-vault ~/Notes
mosaic search "quantum computing" --obsidian --obsidian-folder "Papers/Quantum"
```

Each note gets YAML frontmatter, `>[!abstract]` callout, metadata table, and `[[wikilinks]]`.

---

## Skill Installation

```bash
# Install to current project's .claude/skills/mosaic/ — enables /mosaic in this project
mosaic skill install

# Install globally to ~/.claude/skills/mosaic/ — enables /mosaic in all projects
mosaic skill install --global

# Inspect the bundled skill content
mosaic skill show
```

After installation, restart Claude Code or open a new session. The `/mosaic` slash command will
be available in that project's Claude Code context.

---

## Full Documentation

https://szaghi.github.io/mosaic/

- [Installation guide](https://szaghi.github.io/mosaic/guide/installation)
- [Usage guide](https://szaghi.github.io/mosaic/guide/usage)
- [Sources reference](https://szaghi.github.io/mosaic/guide/sources)
- [RAG guide](https://szaghi.github.io/mosaic/guide/rag)
- [Citation Network guide](https://szaghi.github.io/mosaic/guide/network)
- [Compare Papers guide](https://szaghi.github.io/mosaic/guide/compare)
- [Zotero integration](https://szaghi.github.io/mosaic/guide/zotero)
- [Obsidian integration](https://szaghi.github.io/mosaic/guide/obsidian)
- [Web UI guide](https://szaghi.github.io/mosaic/guide/web-ui)
- [Source code](https://github.com/szaghi/mosaic)
