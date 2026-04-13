---
layout: home

hero:
  name: MOSAIC
  text: Multi-source Scientific Article Indexer and Collector
  tagline: a vivid mosaic of open scientific literature, assembled in seconds
  image:
    light: /mosaic-logo-alpha-black.png
    dark:  /mosaic-logo-alpha-white.png
    alt:   MOSAIC logo
  actions:
    - theme: brand
      text: Get Started
      link: /guide/installation
    - theme: alt
      text: Citation Network
      link: /guide/network
    - theme: alt
      text: Compare Papers
      link: /guide/compare
    - theme: alt
      text: Local RAG Guide
      link: /guide/rag
    - theme: alt
      text: View on GitHub
      link: https://github.com/szaghi/mosaic

features:
  - icon: 🔍
    title: Multi-source Search
    details: Query arXiv, Semantic Scholar, ScienceDirect, Springer Nature (browser + API), DOAJ, Europe PMC, OpenAlex, BASE, CORE, NASA ADS, IEEE Xplore, Zenodo, Crossref, DBLP, HAL, PubMed, PubMed Central, and bioRxiv/medRxiv simultaneously. Results are deduplicated by DOI so you never see the same paper twice.
  - icon: 📄
    title: PDF Download
    details: Download open-access PDFs directly. When no PDF link is known, MOSAIC queries Unpaywall to find a legal open-access copy automatically.
  - icon: 🗄️
    title: Local Cache
    details: All search results and download history are stored in a local SQLite database. Re-run queries instantly without hitting the network.
  - icon: ⚙️
    title: Source-aware
    details: Enable or disable individual sources, set per-source API keys, and control rate limits — all from a single TOML config file.
  - icon: 🖥️
    title: Rich Terminal UI
    details: Results are displayed as a formatted table with open-access and PDF indicators. Progress spinners keep you informed during long searches.
  - icon: 🌐
    title: Web Interface
    details: Launch a browser-based UI with `mosaic ui`. Search, filter, download, and export from a responsive dashboard with dark mode, per-source progress, and keyboard shortcuts.
  - icon: 🧠
    title: Local RAG
    details: Index your paper library and ask questions in natural language — synthesis, gap analysis, method comparison, structured extraction. Runs fully locally via Ollama or any OpenAI-compatible server. No data leaves your machine.
  - icon: 📊
    title: Relevance Ranking
    details: Re-rank any result set by semantic similarity to your query with --sort relevance. BM25 by default (instant, no model). Optionally delegate to your configured LLM for higher-quality scores.
  - icon: 🤖
    title: NotebookLM Integration
    details: Turn any search into a Google NotebookLM notebook — podcast, video overview, slides, quiz, flashcards, mind map, and briefing doc queued in one command with mosaic notebook create.
  - icon: 🕸️
    title: Citation Network
    details: Explore hub papers and topic clusters from your local citation graph. BFS subgraph from any seed query, Louvain or connected-components clustering, and graph export to JSON (D3/Gephi), Graphviz DOT, or Mermaid — all with `mosaic network`.
  - icon: 📋
    title: Compare Papers
    details: Generate a structured comparison table (method, dataset, metric, result) across any set of cached papers using an LLM. Falls back gracefully to metadata fields without one. Export to Markdown, CSV, or JSON with `mosaic compare`.
  - icon: 🦾
    title: Claude Code Skill & AI Agent Mode
    details: Install the bundled Claude Code skill with `mosaic skill install` — gives Claude Code full knowledge of every command, source, and option. The `--json` flag on search and similar emits a structured JSON envelope to stdout for piping, scripting, and CI pipelines.
  - icon: 🔓
    title: Open & Extensible
    details: Each source is a small self-contained class. Adding a new database takes fewer than 50 lines of Python.
  - icon: 🔌
    title: Custom Sources
    details: Wire any number of JSON REST APIs as new search sources directly in config.toml — one block per source, no Python required. Supports GET and POST, nested field paths, API keys, and author objects.
  - icon: 📚
    title: Zotero Integration
    details: Push results directly into your Zotero library with --zotero. Works with Zotero desktop (local API) and Zotero web (api.zotero.org). Organise into named collections and link downloaded PDFs as attachments.
---

## Quick start

```bash
# Core install — all 21 sources and the full CLI
pipx install mosaic-search

# Everything at once — RAG, web UI, Louvain clustering, browser sessions, NotebookLM
pipx install 'mosaic-search[all]'
playwright install chromium   # browser binary (needed for auth and NotebookLM)

mosaic config --unpaywall-email you@example.com
mosaic search "attention is all you need" --oa-only --download
```

## AI features

### Local RAG — mosaic index / ask / chat

Index your cached papers once and interrogate your library in natural language. Four structured analysis modes produce cited, grounded answers:

| Mode | What it produces |
|------|-----------------|
| `synthesis` | Comprehensive state-of-the-art summary |
| `gaps` | Open problems, contradictions, methodological limitations |
| `compare` | Side-by-side comparison of methods, datasets, metrics, results |
| `extract` | Per-paper structured extraction: Task · Method · Dataset · Metric · Result |

```bash
pipx inject mosaic-search sqlite-vec          # install vector extension once

mosaic index                                  # embed all cached papers
mosaic ask "What are the main approaches to graph neural networks?" --show-sources
mosaic ask "What open problems remain in protein structure prediction?" --mode gaps
mosaic chat                                   # interactive multi-turn session
```

Runs entirely on your machine via [Ollama](https://ollama.com) or any OpenAI-compatible server. → [RAG guide](./guide/rag)

---

### Citation network — `mosaic network`

After enriching your cache with citation edges, explore the topology of your corpus: identify hub papers, cluster by community, and export the graph for downstream tools — without leaving the terminal.

```bash
# Enrich the citation graph (OpenAlex + CrossRef edges)
mosaic index --enrich-citations

# Most-connected papers across the full graph
mosaic network --top 10

# Topic subgraph with cluster report
mosaic network --query "transformer attention" --depth 2 --cluster --top 5

# Export for D3.js / Gephi / Mermaid
mosaic network --output graph.json
mosaic network --output graph.md
```

Louvain clustering via `networkx` (`pipx inject mosaic-search networkx`); falls back to connected components automatically.

→ [Citation Network guide](./guide/network)

---

### Compare papers — `mosaic compare`

Generate a structured comparison table across any set of cached papers. With an LLM configured, it extracts dimensions (method, dataset, metric, result) from each abstract. Without one, metadata fields are used and a notice is printed — the command never fails silently.

```bash
# Compare top-cited papers on a topic
mosaic compare --query "diffusion models" --sort citations -n 15 --output comparison.md

# Custom dimensions from a BibTeX file
mosaic compare --from refs.bib --dimensions "method,dataset,BLEU,limitations"
```

→ [Compare Papers guide](./guide/compare)

---

### Relevance ranking — `--sort relevance`

Re-rank any result set by semantic similarity to the query. BM25 by default (no model, no network, instant). Configure your LLM for higher-quality scores.

```bash
mosaic search "diffusion models" --sort relevance          # live, ranked
mosaic search "diffusion models" --cached --sort relevance # offline, from local cache
```

→ [Relevance ranking guide](./guide/relevance-ranking)

---

### NotebookLM — `mosaic notebook`

Turn any search into a Google NotebookLM notebook in one command. Podcast, video overview, slides, quiz, flashcards, mind map, briefing doc — all queued automatically.

```bash
mosaic notebook create "Transformers" --query "attention mechanism" --oa-only --podcast --briefing
```

→ [NotebookLM guide](./guide/notebooklm)

---

### Claude Code Skill & AI agent mode — `mosaic skill install`

MOSAIC ships a bundled [Claude Code](https://claude.ai/claude-code) skill. Install it once and the
`/mosaic` slash command gives Claude Code expert knowledge of every command, source shorthand,
filter, export format, and scripting pattern — so you can describe your bibliography goal in plain
English and let Claude Code build and run the right commands for you.

```bash
# Install into the current project's .claude/skills/ directory
mosaic skill install

# Or globally, for all your projects
mosaic skill install --global
```

All `search` and `similar` commands support `--json` for structured stdout — a clean
`{status, query, count, papers[], errors[]}` envelope designed for piping, agent scripts, and CI:

```bash
# Pipe directly to jq
mosaic search "attention mechanism" --max 30 --oa-only --json \
  | jq -r '.papers[] | "\(.year)  \(.doi)  \(.title)"'

# Combine file export and stdout JSON in one run
mosaic search "FDTD methods" --json --output refs.bib
```

→ [Agent Workflows guide](./guide/agent-workflows)

---

## Architecture

```mermaid
flowchart LR
    CLI -->|query| Search
    Search --> arXiv & SS[Semantic Scholar] & SD[ScienceDirect] & SP[Springer browser] & SPN[Springer API] & DOAJ & EPMC[Europe PMC] & OA[OpenAlex] & BASE & CORE & ADS[NASA ADS] & IEEE[IEEE Xplore] & ZEN[Zenodo] & CR[Crossref] & DBLP[DBLP] & HAL[HAL] & PM[PubMed] & PMC[PubMed Central] & RXV[bioRxiv/medRxiv]
    arXiv & SS & SD & SP & SPN & DOAJ & EPMC & OA & BASE & CORE & ADS & IEEE & ZEN & CR & DBLP & HAL & PM & PMC & RXV -->|Paper list| Dedup
    Dedup -->|unique papers| Cache[(SQLite)]
    Dedup --> Table[Rich table]
    Table -->|download flag| DL[Downloader]
    DL -->|no pdf_url| UPW[Unpaywall]
    UPW -->|pdf url| DL
    DL --> Disk[(~/mosaic-papers/)]
```

## Authors

**[Stefano Zaghi](https://github.com/szaghi)** · stefano.zaghi@gmail.com
> *Chief Yak Shaver & Accidental Package Maintainer* — Fortran programmer who needed one paper, opened 21 browser tabs, and six months later found himself maintaining a Python library

**[Andrea Giulianini](https://github.com/AndreaGiulianini)**
> *Grand Pixel Overlord & Architect of the Sacred Button* — world-class web UI designer, responsible for making MOSAIC actually look good

**[Claude](https://claude.ai)** (Anthropic)
> *Omniscient Code Oracle & Tireless Rubber Duck* — AI pair programmer, responsible for writing the boring parts so humans don't have to

Contributions are welcome.

## License

MOSAIC is available under your choice of license: GPL-3.0-or-later, BSD-2-Clause, BSD-3-Clause, or MIT.
See [LICENSE.gpl3.md](https://github.com/szaghi/mosaic/blob/main/licensing/LICENSE.gpl3.md), [LICENSE.bsd-2.md](https://github.com/szaghi/mosaic/blob/main/licensing/LICENSE.bsd-2.md), [LICENSE.bsd-3.md](https://github.com/szaghi/mosaic/blob/main/licensing/LICENSE.bsd-3.md), [LICENSE.mit.md](https://github.com/szaghi/mosaic/blob/main/licensing/LICENSE.mit.md).

© [Stefano Zaghi](https://github.com/szaghi)
