---
title: Searching
---

# Searching

Recipes for finding papers: which sources to ask, which filters to apply, and how to search what you already have.

[[toc]]

## Everything on a topic

```bash
mosaic search "hall thruster particle-in-cell"
mosaic search "hall thruster particle-in-cell" --max 25      # 25 per source instead of 10
```

mosaic asks every enabled source at once, eight at a time, and merges the papers that several sources return.
`--max` counts per source, so the table usually holds more rows than `--max`.
Tutorial: [a first search](/tutorial/01-first-search). Guide: [Sources](/guide/sources).

## One database

```bash
mosaic search "hall thruster" --source arxiv
mosaic search "hall thruster" -s oa          # OpenAlex
```

The shorthands: `arxiv`, `ss` (Semantic Scholar), `sd` (ScienceDirect), `sp` (Springer, browser), `springer`
(Springer Nature API), `doaj`, `epmc` (Europe PMC), `cochrane`, `oa` (OpenAlex), `base`, `core`, `ads` (NASA ADS),
`ieee`, `zenodo`, `crossref`, `dblp`, `hal`, `pubmed`, `pmc`, `rxiv` (bioRxiv/medRxiv), `pedro`, `scopus`. A source
that needs a key you have not set is reported as not active.
Guide: [Sources](/guide/sources).

## Title or abstract only

```bash
mosaic search "hall thruster" --field title
mosaic search "anomalous transport" -f abstract --source arxiv
```

Each source receives the query in its own field syntax (`ti:` on arXiv, `title.search` on OpenAlex). Without
`--field`, most sources search title, abstract and keywords together.
Tutorial: [narrowing the results](/tutorial/02-narrowing#only-the-title).

## A year range or a list of years

```bash
mosaic search "hall thruster" --year 2020-2025     # inclusive range
mosaic search "hall thruster" -y 2023              # one year
mosaic search "hall thruster" -y 2019,2021,2023    # a list
```

mosaic passes the years to the sources that support them, then checks every result again.

## By author

```bash
mosaic search "hall thruster" --author Boeuf
mosaic search "hall thruster" -a Boeuf -a Garrigues     # either of them
```

The match is a part of any author's name, ignoring case and accents: `Boeuf` finds "Jean-Pierre Bœuf". Repeated
`--author` options mean "any of these".
Tutorial: [an author](/tutorial/02-narrowing#an-author).

## By journal

```bash
mosaic search "hall thruster" --journal "Physics of Plasmas"
```

`--journal` matches part of the journal name, ignoring case. Preprints have no journal, so they drop out.

## Open access only, or with a PDF

```bash
mosaic search "hall thruster anomalous transport" --oa-only     # open access or a PDF link
mosaic search "hall thruster anomalous transport" --pdf-only    # a PDF link
```

These are the papers `--download` gets without further help.
Tutorial: [open access, with a PDF](/tutorial/02-narrowing#open-access-with-a-pdf).

## Most cited or newest first

```bash
mosaic search "hall thruster" --sort citations
mosaic search "hall thruster" --sort year
```

`--sort citations` adds a Cited column with the counts that OpenAlex, Semantic Scholar and Scopus report; papers
from other sources have none and come last. `--sort relevance` ranks by similarity to the query: see
[Relevance ranking](/guide/relevance-ranking).

## The source's own query language

```bash
mosaic search "" --source arxiv --raw-query 'ti:"hall thruster" AND abs:kinetic'
```

`--raw-query` goes to each source unchanged, skipping the field, author and journal translation. Use it with one
`--source`: other sources do not understand arXiv syntax. Year filters still apply to the results.

## Why a source returned nothing

```bash
mosaic --verbose search "hall thruster" --stats
```

`--verbose`, written before the command, prints one warning per source that failed (a rate limit, a timeout, a
bot-check page). `--stats` counts the results of each source, the duplicates merged and the unique papers left.
Tutorial: [which sources answered](/tutorial/01-first-search#which-sources-answered). Guide:
[rate limits and quotas](/guide/sources#rate-limits-and-quotas).

## Search what you already found

```bash
mosaic search "thruster simulation" --cached
mosaic search "thruster simulation" --cached --sort year --oa-only
```

`--cached` searches the local cache only: no network, no keys. Every word of the query must appear in the title or
the abstract, in any order. Every result of every earlier search, `similar` and `get` is in the cache.
Tutorial: [the local cache](/tutorial/03-cache). Guide: [The cache](/guide/cache).

## Prefer complete cached records

```bash
mosaic search "hall thruster particle-in-cell" --prefer-cache
```

For a paper whose cached record has title, year, authors and abstract, mosaic shows that record in place of the
one the source returns now. Useful when earlier searches built richer records than a source gives today.
Guide: [`--prefer-cache`](/guide/cache#prefer-cache).

## Add a source that needs a key

```bash
mosaic config --ss-key KEY          # Semantic Scholar: fewer rate limits
mosaic config --core-key KEY        # CORE
mosaic config --ads-key TOKEN       # NASA ADS
mosaic config --ieee-key KEY        # IEEE Xplore
mosaic config --springer-key KEY    # Springer Nature API
mosaic config --ncbi-key KEY        # PubMed and PubMed Central: higher quota
mosaic config --elsevier-key KEY    # ScienceDirect
mosaic config --scopus-key KEY      # Scopus
mosaic config --zenodo-key TOKEN    # Zenodo
```

The keys are free for personal research use; [Sources](/guide/sources#notes-per-source) links each sign-up page. A
source with a key joins every search from then on.
Guide: [API keys](/guide/configuration#api-keys).

## Turn off a noisy source

```bash
mosaic config --disable-source cochrane
mosaic config --enable-source cochrane
```

These flags take the configuration names, not the `--source` shorthands: `arxiv`, `semantic_scholar`,
`sciencedirect`, `doaj`, `europepmc`, `cochrane`, `openalex`, `base`, `springer_api`, `springer`, `core`,
`nasa_ads`, `ieee`, `zenodo`, `crossref`, `dblp`, `hal`, `pubmed`, `pmc`, `biorxiv`, `pedro`, `scopus`.
`--stats` shows which sources never return anything for your field.

## A JSON API of your own

```toml
# ~/.config/mosaic/config.toml
[[custom_sources]]
name         = "My repository"
url          = "https://repo.example.org/api/search"
query_param  = "q"
results_path = "results"

[custom_sources.fields]
title = "title"
doi   = "doi"
year  = "published"
```

A custom source maps the fields of a JSON search API to papers, with no Python: `results_path` names the array of
results in the answer, `[custom_sources.fields]` the path of each paper field in a result. Keys of the source
itself go above the `fields` table.
Guide: [Custom sources](/guide/custom-sources).
