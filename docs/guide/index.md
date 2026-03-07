---
title: About MOSAIC
---

# About MOSAIC

#### *a vivid mosaic of open scientific literature, assembled in seconds*

**MOSAIC** (Multi-sOurce Scientific Article Indexer and Collector) is a command-line tool for searching and downloading scientific papers from multiple open (and closed, if allowed) bibliographic databases.

Instead of visiting a dozen or more different websites to hunt for a paper, MOSAIC queries them all simultaneously, deduplicates results by DOI, and downloads open-access PDFs — including those found via Unpaywall — in one shot. Results can also be sent directly to a Google NotebookLM notebook for AI-powered Q&A, audio overviews, video summaries, slide decks, mind maps, flashcards, quizzes, infographics, study guides, and more.

## Why MOSAIC?

Finding scientific papers across databases is tedious:

- Each database has its own search syntax and web interface
- The same paper often appears in multiple databases under slightly different metadata
- Locating a free legal PDF requires checking the journal site, arXiv, PubMed Central, and institutional repositories
- There is no programmatic way to keep a local archive of your searches
- There is no automatic summary creation for bibliographics collections

MOSAIC solves all of this in a single command.

## Design principles

- **One command, many sources** — fan-out search with transparent deduplication
- **Legal open-access only by default** — no paywall circumvention
- **Closed-access** — supported by users API key (if provided, e.g. Elsevier source)
- **Minimal dependencies** — `httpx`, `typer`, `rich`, `tomli-w`; no heavy frameworks
- **Offline-friendly** — local SQLite cache means repeated queries are instant
- **Extensible** — each source is an independent class; adding a new one takes ~50 lines
- **Custom sources** — wire any number of JSON REST APIs as new sources with a few lines of TOML each, no Python needed
- **AI-powered artifacts creation (summary, presentation, podcast, ecc...)** by [Google NotebookLM](https://notebooklm.google.com/)

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
