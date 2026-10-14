---
layout: home

hero:
  name: MOSAIC
  text: One search, two dozen scientific databases
  tagline: Search arXiv, OpenAlex, Crossref, PubMed, HAL, Semantic Scholar and 16 more at once, keep every result in a local library, download the PDFs you are entitled to read, and ask a language model about them, on your machine.
  image:
    light: /mosaic-logo-alpha-black.png
    dark:  /mosaic-logo-alpha-white.png
    alt:   MOSAIC logo
  actions:
    - theme: brand
      text: Tutorial
      link: /tutorial/
    - theme: alt
      text: Install
      link: /guide/installation
    - theme: alt
      text: Cookbook
      link: /cookbook/
    - theme: alt
      text: Reference
      link: /reference/
    - theme: alt
      text: View on GitHub
      link: https://github.com/szaghi/mosaic

features:
  - icon: 🔍
    title: Every database in one query
    details: 22 sources searched in parallel, from arXiv and OpenAlex to PubMed, IEEE Xplore and Scopus. Duplicates merged by DOI; filters by year, author, journal, title or abstract, and the source's own syntax when you need it.
    link: /tutorial/01-first-search
    linkText: A first search
  - icon: 📄
    title: The PDFs you can read
    details: The source's link, then every open copy Unpaywall knows, then your saved publisher logins. Each file is checked to be a real PDF and named after the paper.
    link: /tutorial/04-pdfs
    linkText: Getting the PDFs
  - icon: 🔐
    title: Paywalls, legally
    details: Where a publisher blocks automation, mosaic opens the article in your own browser and files the PDF you download. PDFs you already have are imported by their DOI.
    link: /tutorial/05-paywalls
    linkText: Paywalled papers
  - icon: 🗄️
    title: A library that grows
    details: Every result goes into a local SQLite cache that fills in what one source leaves out. Search it offline; export it to BibTeX, RIS, CSV, JSON, Zotero or Obsidian.
    link: /tutorial/03-cache
    linkText: The cache
  - icon: 📡
    title: Following a field
    details: Saved searches report only the papers they have not shown you before; one cron line makes a morning digest. Related papers from any seed paper.
    link: /tutorial/07-following
    linkText: Following a field
  - icon: 🧠
    title: A model that reads with you
    details: Relevance ranking, one-paragraph summaries that cite the rows, comparison tables, and questions answered from your papers with citations. Ollama on your machine, or a cloud API.
    link: /tutorial/08-local-model
    linkText: A local model
  - icon: 🕸️
    title: The citation map
    details: Citation links between the papers of your library, hub papers, clusters, and graph files for Gephi, Graphviz or Mermaid.
    link: /tutorial/10-citations
    linkText: The citation network
  - icon: 🤖
    title: Scripts and agents
    details: JSON output for jq and pipelines, exit codes that report failures, a Claude Code skill, and a web interface for colleagues who prefer a browser.
    link: /cookbook/scripting
    linkText: Scripts and agents
---

<div class="mosaic-home">

## One query, every source

<p class="mosaic-lead">The sources answer in parallel; mosaic merges what they return into one table and keeps it.</p>

<img src="/gifs/search.gif" alt="mosaic search: a spinner while the sources answer, then one merged table of results">

## Quick start

```bash
pipx install 'mosaic-search[all]'
mosaic config --unpaywall-email you@example.org

mosaic search "hall thruster particle-in-cell" --oa-only --download
mosaic get 10.3389/fphy.2019.00140
mosaic search "hall thruster" --cached --output refs.bib
```

<p class="mosaic-lead">Then the <a href="./tutorial/">tutorial</a>: ten chapters, one literature search, real output.</p>

## A paywalled paper, through your own browser

<p class="mosaic-lead">The terminal side of <code>mosaic get --handoff</code>: the article opens in your browser, you
click Download, and mosaic files the PDF under the paper's name.</p>

<img src="/gifs/handoff.gif" alt="mosaic get --handoff: the article opens in the browser, the downloaded PDF is moved into the library">

## A paragraph instead of thirty abstracts

<img src="/gifs/summarise.gif" alt="mosaic search --summarise: the results table, then a paragraph citing the rows by number">

</div>
