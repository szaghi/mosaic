---
title: About MOSAIC
---

# About MOSAIC

**MOSAIC** (Multi-source Scientific Article Index and Collector) is a command-line tool for searching and downloading scientific papers from multiple open bibliographic databases.

Instead of visiting five different websites to find a paper, MOSAIC queries them all at once, deduplicates the results by DOI, and — when a PDF is available — downloads it to your local disk.

## Why MOSAIC?

Finding scientific papers across databases is tedious:

- Each database has its own search syntax and web interface
- The same paper often appears in multiple databases under slightly different metadata
- Locating a free legal PDF requires checking the journal site, arXiv, PubMed Central, and institutional repositories
- There is no programmatic way to keep a local archive of your searches

MOSAIC solves all of this in a single command.

## Design principles

- **One command, many sources** — fan-out search with transparent deduplication
- **Legal open-access only by default** — no paywall circumvention
- **Minimal dependencies** — `httpx`, `typer`, `rich`, `tomli-w`; no heavy frameworks
- **Offline-friendly** — local SQLite cache means repeated queries are instant
- **Extensible** — each source is an independent class; adding a new one takes ~50 lines

## Authors

- Stefano Zaghi — [@szaghi](https://github.com/szaghi)

## License

MOSAIC is available under your choice of license:

| License | SPDX |
|---|---|
| GNU General Public License v3 | `GPL-3.0-or-later` |
| BSD 2-Clause | `BSD-2-Clause` |
| BSD 3-Clause | `BSD-3-Clause` |
| MIT | `MIT` |

© [Stefano Zaghi](https://github.com/szaghi)
