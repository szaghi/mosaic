<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="docs/public/mosaic-logo-alpha-white.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/public/mosaic-logo-alpha-black.png">
  <img src="docs/public/mosaic-logo-alpha-black.png" alt="MOSAIC logo" width="480">
</picture>

#### *a vivid mosaic of open scientific literature, assembled in seconds*

### Multi-sOurce Scientific Article Indexer and Collector

>Search, discover, and download scientific papers from multiple open databases — with a single command.
>Send results directly to [Google NotebookLM](https://notebooklm.google.com/) for AI-powered summaries, podcasts, and more.

[![Version](https://img.shields.io/github/v/release/szaghi/mosaic?label=version)](https://github.com/szaghi/mosaic/releases/latest)
[![Tests](https://github.com/szaghi/mosaic/actions/workflows/tests.yml/badge.svg)](https://github.com/szaghi/mosaic/actions/workflows/tests.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://szaghi.github.io/mosaic/coverage-badge.json)](https://szaghi.github.io/mosaic/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/license-GPL%20v3-blue)](LICENSE.gpl3.md)
[![License: BSD-2](https://img.shields.io/badge/license-BSD--2--Clause-blue)](LICENSE.bsd-2.md)
[![License: BSD-3](https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE.bsd-3.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE.mit.md)

**[Full documentation](https://szaghi.github.io/mosaic/)**

</div>

---

## What MOSAIC does

```bash
# Search 19 sources at once, deduplicate, download OA PDFs
mosaic search "attention is all you need" --oa-only --download

# Discover related literature from any DOI or arXiv ID — no query needed
mosaic similar 10.48550/arXiv.1706.03762 --sort citations

# Bulk-download your entire Zotero / JabRef library
mosaic get --from refs.bib --oa-only

# Turn results into an AI-powered notebook: podcast, slides, quiz, mind map…
mosaic notebook create "Transformers" --query "transformer architecture" --oa-only --podcast
```

![MOSAIC quick search demo](docs/public/gifs/01_quick_search.gif)

## Key features

<table>
<tr>
<td align="center" width="33%">

🌐 **19 sources, one command**

arXiv · Semantic Scholar · OpenAlex · PubMed · PubMed Central · Europe PMC · DOAJ · Crossref · Springer · IEEE · NASA ADS · Zenodo · BASE · CORE · DBLP · HAL · ScienceDirect · and more

</td>
<td align="center" width="33%">

🔭 **Find similar papers**

`mosaic similar <doi>` — discover related literature from any DOI or arXiv ID via OpenAlex graph + Semantic Scholar ML, no query needed

</td>
<td align="center" width="33%">

✨ **Smart deduplication**

Results merged by DOI: best citation count, richest abstract, earliest PDF URL wins

</td>
</tr>
<tr>
<td align="center">

📥 **OA PDF downloads**

Direct links · Unpaywall fallback · browser-session authenticated access · bulk download from `.bib`/`.csv`

</td>
<td align="center">

🎛️ **Sort & filter**

Year · author · journal · open-access · citation count — composable, applied at API level where supported

</td>
<td align="center">

📤 **Export anywhere**

Markdown · CSV · JSON · BibTeX — one flag, any combination

</td>
</tr>
<tr>
<td align="center">

🤖 **NotebookLM integration**

Podcast · video · slides · quiz · mind map · flashcards · briefing — queued in one command

</td>
<td align="center">

⚡ **Offline-first cache**

SQLite — repeated queries are instant, no re-fetching

</td>
<td align="center">

🧩 **Custom sources**

Wire any JSON REST API as a new source with a few lines of TOML — no Python needed

</td>
</tr>
</table>

## Sources

| Source | Shorthand | Coverage | Auth | OA PDF |
|---|---|---|---|---|
| **arXiv** | `arxiv` | Physics, CS, Math, Biology… | None | Always |
| **Semantic Scholar** | `ss` | 214 M papers, all disciplines | Optional key | When indexed |
| **ScienceDirect** | `sd` | Elsevier journals & books | API key or browser session | OA articles |
| **Springer Nature** | `sp` | Springer, Nature & affiliated journals (browser) | None (`[browser]` extra) | Via Unpaywall |
| **Springer Nature API** | `springer` | OA articles from Springer, Nature & affiliated journals | Free API key | Direct PDF link |
| **DOAJ** | `doaj` | 8 M+ fully open-access articles | None | Always |
| **Europe PMC** | `epmc` | 45 M biomedical papers | None | PMC articles |
| **OpenAlex** | `oa` | 250 M+ works, all disciplines | None | When available |
| **BASE** | `base` | 300 M+ docs from 10 000+ repos | None | When OA + PDF format |
| **CORE** | `core` | 200 M+ OA full-text from repos | Free API key | `downloadUrl` field |
| **NASA ADS** | `ads` | 15 M+ astronomy & astrophysics records | Free API token | OA articles |
| **IEEE Xplore** | `ieee` | 5 M+ IEEE journals, transactions & conference proceedings | Free API key | OA articles |
| **Zenodo** | `zenodo` | 3 M+ OA research outputs (papers, datasets, software) | None (token optional) | Attached PDF files |
| **Crossref** | `crossref` | 150 M+ scholarly works (DOI registry) | None (email optional) | When deposited by publisher |
| **DBLP** | `dblp` | 6 M+ CS publications (journals, conferences) | None | Via `ee` field (arXiv/OA links) |
| **HAL** | `hal` | 1.5 M+ OA documents, strong for French academic output | None | Direct PDF when deposited |
| **PubMed** | `pubmed` | 35 M+ biomedical citations (NCBI) | None (API key optional) | PMC PDF for OA articles |
| **PubMed Central** | `pmc` | 5 M+ free full-text biomedical articles | None (API key optional) | Always — all PMC articles are OA |
| **Unpaywall** | — | PDF resolver for any DOI | Email only | Legal OA copy |

## Installation

```bash
# recommended — isolated install, globally available
pipx install mosaic-search        # or: uv tool install mosaic-search
```

```bash
# pip — must be inside a virtualenv (modern systems enforce PEP 668)
python -m venv ~/.venvs/mosaic && source ~/.venvs/mosaic/bin/activate
pip install mosaic-search
```

```bash
# from source
git clone https://github.com/szaghi/mosaic
cd mosaic
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

> Requires Python 3.11+

## Quick Start

```bash
# 1. Set your email (enables Unpaywall PDF fallback)
mosaic config --unpaywall-email you@example.com

# 2. Optional: add an Elsevier API key to unlock ScienceDirect
mosaic config --elsevier-key YOUR_KEY

# 3. Search and download
mosaic search "transformer architecture" --oa-only --download
```

![MOSAIC search and download demo](docs/public/gifs/02_search_download.gif)

## Usage

### Search

```bash
# Search all enabled sources (10 results per source by default)
mosaic search "protein folding"

# More results, open-access only
mosaic search "deep learning" -n 25 --oa-only

# Single source
mosaic search "RNA velocity" --source epmc
```

**Source shorthands:** `arxiv` · `ss` · `sd` · `doaj` · `epmc` · `oa` · `base` · `core`

Custom sources defined in `config.toml` are also queried and addressable by their `name`.

### Filters

```bash
# By year — single, range, or list
mosaic search "BERT" --year 2019
mosaic search "diffusion models" -y 2020-2023
mosaic search "GPT" -y 2020,2022,2024

# By author (repeatable, OR logic, case-insensitive substring)
mosaic search "attention" -a Vaswani -a Shazeer

# By journal (case-insensitive substring)
mosaic search "CRISPR" --journal "Nature"

# Combine freely
mosaic search "graph neural" -y 2021-2023 -a Kipf -j "ICLR" --oa-only --download
```

### Find similar papers

```bash
# Discover related literature from any DOI or arXiv ID
mosaic similar 10.48550/arXiv.1706.03762

# Sort by citation count, open-access only
mosaic similar arxiv:1706.03762 -n 20 --sort citations --oa-only

# Save to BibTeX
mosaic similar 10.1038/s41586-021-03819-2 --output related.bib
```

Uses **OpenAlex** `related_works` (always) and **Semantic Scholar** recommendations (when `ss-key` is configured). Results are deduplicated and merged — the higher citation count and richer metadata always win.

### Download by DOI

```bash
mosaic get 10.48550/arXiv.1706.03762
```

Checks the local cache first, then tries Unpaywall if no PDF URL is known.

### Bulk download from BibTeX / CSV

```bash
# Export your Zotero/JabRef/Mendeley library and download everything
mosaic get --from refs.bib

# CSV with a 'doi' column works too
mosaic get --from references.csv --oa-only
```

Extracts all DOIs from the file, deduplicates, and downloads with the same fallback chain (direct PDF → Unpaywall → browser session).

### Configuration

```bash
mosaic config --show                          # print current config
mosaic config --unpaywall-email me@uni.edu
mosaic config --elsevier-key abc123
mosaic config --ss-key xyz789
mosaic config --download-dir ~/papers
```

Config is stored at `~/.config/mosaic/config.toml`. Downloaded PDFs go to `~/mosaic-papers/` by default.

### Custom sources

Any number of JSON REST APIs can be added as new sources directly in `config.toml` — one `[[custom_sources]]` block per source, no Python required:

```toml
[[custom_sources]]
name         = "My Institution Repo"
enabled      = true
url          = "https://repo.myuni.edu/api/search"
method       = "GET"
query_param  = "q"
results_path = "results"

[custom_sources.fields]
title    = "title"
doi      = "doi"
year     = "year"
authors  = "authors"    # flat string array
journal  = "source.title"
```

See the [Custom Sources guide](https://szaghi.github.io/mosaic/guide/custom-sources) for the full reference.

### NotebookLM

Send search results directly to a Google NotebookLM notebook:

```bash
# 1. Inject into MOSAIC (--include-apps exposes the notebooklm CLI)
pipx inject --include-apps mosaic-search "notebooklm-py[browser]"

# 2. Install Chromium — playwright lives inside the pipx venv, call it directly
~/.local/share/pipx/venvs/mosaic-search/bin/playwright install chromium

# 3. Authenticate once
notebooklm login

# 4. Search, download, and create a notebook in one command
mosaic notebook create "Transformers" --query "transformer architecture" --oa-only --podcast

# Or import PDFs you already have
mosaic notebook create "My Papers" --from-dir ~/mosaic-papers/
```

MOSAIC uploads local PDFs when available, falls back to URLs otherwise, and respects NotebookLM's 50-source limit. With `--podcast`, an Audio Overview is queued automatically.

## Architecture

```mermaid
flowchart LR
    CLI -->|query + filters| Search
    Search --> arXiv & SS[Semantic Scholar] & SD[ScienceDirect] & SP[Springer browser] & SPN[Springer API] & DOAJ & EPMC[Europe PMC] & OA[OpenAlex] & BASE & CORE & ADS[NASA ADS] & IEEE[IEEE Xplore] & ZEN[Zenodo] & CR[Crossref] & DBLP[DBLP] & HAL[HAL] & PM[PubMed] & PMC[PubMed Central]
    arXiv & SS & SD & SP & SPN & DOAJ & EPMC & OA & BASE & CORE & ADS & IEEE & ZEN & CR & DBLP & HAL & PM & PMC -->|Paper list| Dedup{Deduplicate\nby DOI}
    Dedup --> Cache[(SQLite\ncache)]
    Dedup --> Table[Rich table]
    Table -->|--download| DL[Downloader]
    DL -->|no pdf_url| UPW[Unpaywall]
    UPW --> DL
    DL -->|no OA copy| AUTH[Browser session]
    AUTH --> DL
    DL --> Disk[(~/mosaic-papers/)]
    DL -->|mosaic notebook create| NLM[NotebookLM]
```

## Development

```bash
pip install -e ".[dev]"

# with NotebookLM integration (includes Playwright for auth)
pip install -e ".[dev,notebooklm]"
playwright install chromium

# run tests + coverage
pytest

# live docs
cd docs && npm install && npm run docs:dev
```

Coverage report and badge JSON are written to `docs/public/` after every test run.

## License

MOSAIC is available under your choice of license:

| License | SPDX | File |
|---|---|---|
| GNU General Public License v3 | `GPL-3.0-or-later` | [LICENSE.gpl3.md](LICENSE.gpl3.md) |
| BSD 2-Clause | `BSD-2-Clause` | [LICENSE.bsd-2.md](LICENSE.bsd-2.md) |
| BSD 3-Clause | `BSD-3-Clause` | [LICENSE.bsd-3.md](LICENSE.bsd-3.md) |
| MIT | `MIT` | [LICENSE.mit.md](LICENSE.mit.md) |

© [Stefano Zaghi](https://github.com/szaghi)
