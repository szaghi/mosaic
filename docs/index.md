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
      text: CLI Reference
      link: /guide/cli-reference
    - theme: alt
      text: View on GitHub
      link: https://github.com/szaghi/mosaic

features:
  - icon: 🔍
    title: Multi-source Search
    details: Query arXiv, Semantic Scholar, ScienceDirect, Springer Nature (browser + API), DOAJ, Europe PMC, OpenAlex, BASE, CORE, NASA ADS, Zenodo, and Crossref simultaneously. Results are deduplicated by DOI so you never see the same paper twice.
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
  - icon: 🔓
    title: Open & Extensible
    details: Each source is a small self-contained class. Adding a new database takes fewer than 50 lines of Python.
  - icon: 🔌
    title: Custom Sources
    details: Wire any number of JSON REST APIs as new search sources directly in config.toml — one block per source, no Python required. Supports GET and POST, nested field paths, API keys, and author objects.
---

## Quick start

```bash
pipx install mosaic-search   # or: uv tool install mosaic-search
mosaic config --unpaywall-email you@example.com
mosaic search "attention is all you need" --oa-only --download
```

## Architecture

```mermaid
flowchart LR
    CLI -->|query| Search
    Search --> arXiv & SS[Semantic Scholar] & SD[ScienceDirect] & SP[Springer browser] & SPN[Springer API] & DOAJ & EPMC[Europe PMC] & OA[OpenAlex] & BASE & CORE & ADS[NASA ADS] & ZEN[Zenodo] & CR[Crossref]
    arXiv & SS & SD & SP & SPN & DOAJ & EPMC & OA & BASE & CORE & ADS & ZEN & CR -->|Paper list| Dedup
    Dedup -->|unique papers| Cache[(SQLite)]
    Dedup --> Table[Rich table]
    Table -->|download flag| DL[Downloader]
    DL -->|no pdf_url| UPW[Unpaywall]
    UPW -->|pdf url| DL
    DL --> Disk[(~/mosaic-papers/)]
```

## Authors

- Stefano Zaghi — [@szaghi](https://github.com/szaghi)

Contributions are welcome.

## License

MOSAIC is available under your choice of license: GPL-3.0-or-later, BSD-2-Clause, BSD-3-Clause, or MIT.
See [LICENSE.gpl3.md](https://github.com/szaghi/mosaic/blob/main/LICENSE.gpl3.md), [LICENSE.bsd-2.md](https://github.com/szaghi/mosaic/blob/main/LICENSE.bsd-2.md), [LICENSE.bsd-3.md](https://github.com/szaghi/mosaic/blob/main/LICENSE.bsd-3.md), [LICENSE.mit.md](https://github.com/szaghi/mosaic/blob/main/LICENSE.mit.md).

© [Stefano Zaghi](https://github.com/szaghi)
