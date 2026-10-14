---
pageClass: tutorial-page
aside: false
title: 1. A first search
---

# 1. A first search

You want the papers that simulate Hall thrusters with particle-in-cell codes. One command asks every database
mosaic can reach:

<<< @/examples/output/01/search.txt{console}

- `--max 5` asks each source for five results (the default is ten). A dozen sources answered, so the table has
  far more rows than five, after mosaic merged the papers that more than one source returned.
- The sources run in parallel, up to eight at a time, behind a spinner. A search takes 10–30 seconds, most of it
  spent waiting for the slowest database. Rows come in the order the sources answered.
- When two sources return the same paper, it appears once, with the richer of the two records. Papers are the
  same when their DOI matches, or their arXiv ID, or (with neither) their title.
- **OA** says whether the paper is open access, **PDF** whether mosaic knows a link to its PDF. **Cited** appears
  when a source reported citation counts.

## Which sources answered

With no configuration, mosaic queries the sources that need no key: arXiv, Semantic Scholar, DOAJ, Europe PMC,
Cochrane, OpenAlex, BASE, Zenodo, Crossref, DBLP, HAL, PubMed, PubMed Central and bioRxiv/medRxiv. The others
(ScienceDirect, Scopus, Springer Nature, IEEE Xplore, CORE, NASA ADS) join when you give them a free API key or a
browser session; [Sources](/guide/sources) lists what each one needs.

A source that fails does not stop the search: the others still answer, and the failure stays hidden. Put
`--verbose` before the command to see why a source is missing:

<<< @/examples/output/01/verbose.txt{console}

Without an API key, Semantic Scholar shares a public quota and often answers HTTP 429, "too many requests";
mosaic retries short waits before it gives up. DBLP sometimes answers scripts with a "making sure you're not a
bot" page instead of results.

## The query

Each source receives the query in its own syntax. For most of them it is a full-text search of title, abstract and
keywords, so this broad query also finds papers that only mention a Hall thruster in passing. The next chapter
narrows it.

::: tip What you learned
`mosaic search` asks every enabled source at once, merges duplicates and prints one table; `--max` counts per
source; `--verbose` shows the sources that failed. Reference: [`search`](/reference/search),
[Sources](/guide/sources).
:::

Next: [2. Narrowing the results](./02-narrowing).
