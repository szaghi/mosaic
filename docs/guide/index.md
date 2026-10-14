---
title: About
---

<img src="/mosaic-logo-alpha-black.png" alt="MOSAIC logo" width="420" class="light-only">
<img src="/mosaic-logo-alpha-white.png" alt="MOSAIC logo" width="420" class="dark-only">

# About

MOSAIC (Multi-source Scientific Article Indexer and Collector) is a command-line tool that searches 22 scientific
databases with one query, keeps every result in a local SQLite cache, and downloads the PDFs you are entitled to
read. On top of that library it exports to BibTeX, RIS, Zotero and Obsidian, follows a field with saved searches,
and lets a language model rank, summarise, compare and answer questions from your papers.

## What it does

| You want to | mosaic | Start with |
|---|---|---|
| find papers on a topic in every database at once | `search` merges arXiv, OpenAlex, Crossref, PubMed, HAL, Semantic Scholar and 16 more | [Tutorial 1](/tutorial/01-first-search) |
| narrow by year, author, journal, title, open access | filters applied by each source and again on every result | [Tutorial 2](/tutorial/02-narrowing) |
| get the PDFs | the source's link, every open copy Unpaywall knows, your saved logins, your own browser | [Tutorial 4](/tutorial/04-pdfs), [5](/tutorial/05-paywalls) |
| put them in your tools | BibTeX, RIS, CSV, JSON, Markdown, Zotero, Obsidian, NotebookLM | [Tutorial 6](/tutorial/06-exporting) |
| hear about new papers | saved searches that report what is new | [Tutorial 7](/tutorial/07-following) |
| read less | relevance ranking, one-paragraph summaries, comparison tables | [Tutorial 8](/tutorial/08-local-model) |
| ask your library | answers with citations from your papers, on your machine | [Tutorial 9](/tutorial/09-library) |

## Principles

- **Legal access only.** mosaic downloads open-access copies and what your own subscriptions open. It does not
  get past paywalls, access controls or bot detection; where a publisher blocks automation, it hands the download
  to your browser.
- **Your data stays local.** The cache, the PDFs and the vector index live in your home directory. A language
  model runs where you point it: on your machine with Ollama, or a cloud API you choose.
- **Few dependencies.** The core needs httpx, typer, rich, tomli-w and rank-bm25; heavier features are extras.
- **Every source is a small class.** Adding a database means one module; adding a JSON API needs a few lines in
  the config file ([Custom sources](./custom-sources)).

## Where to start

New to mosaic: [Installation](./installation), then the [Tutorial](/tutorial/). Looking for one task: the
[Cookbook](/cookbook/). Looking up an option: the [Reference](/reference/).

## Authors

**[Stefano Zaghi](https://github.com/szaghi)**
> *Chief Yak Shaver & Accidental Package Maintainer* — Fortran programmer who needed one paper, opened 21 browser tabs, and six months later found himself maintaining a Python library

**[Andrea Giulianini](https://github.com/AndreaGiulianini)**
> *Grand Pixel Overlord & Architect of the Sacred Button* — world-class web UI designer, responsible for making MOSAIC actually look good

**[Claude](https://claude.ai)** (Anthropic)
> *Omniscient Code Oracle & Tireless Rubber Duck* — AI pair programmer, responsible for writing the boring parts so humans don't have to

## License

MOSAIC is free software, under your choice of
[GPL-3.0-or-later](https://github.com/szaghi/mosaic/blob/main/licensing/LICENSE.gpl3.md),
[BSD-2-Clause](https://github.com/szaghi/mosaic/blob/main/licensing/LICENSE.bsd-2.md),
[BSD-3-Clause](https://github.com/szaghi/mosaic/blob/main/licensing/LICENSE.bsd-3.md) or
[MIT](https://github.com/szaghi/mosaic/blob/main/licensing/LICENSE.mit.md).
