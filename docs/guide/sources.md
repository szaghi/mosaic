---
title: Sources
---

# Sources

`mosaic search` queries up to 22 bibliographic sources at once, eight at a time, and merges the results by DOI. A
source runs when it is enabled in the config and has what it needs (an API key, a browser, a saved login); the
others are skipped without a message. Pass `--source SHORTHAND` to query one source only, and
`mosaic --verbose search ...` to see the warnings of sources that failed.

| Source | `--source` | Covers | Access | PDF links |
|---|---|---|---|---|
| arXiv | `arxiv` | Preprints: physics, mathematics, CS, quantitative biology, finance | none | every result |
| Semantic Scholar | `ss` | All disciplines | none; key optional | when it lists an open copy |
| ScienceDirect | `sd` | Elsevier journals and books | API key or browser session | open-access articles (API mode) |
| Springer (browser) | `sp` | Springer and Nature journals, books | Playwright browser | none; resolved at download |
| Springer Nature API | `springer` | Springer Nature open-access articles | key required | when deposited |
| DOAJ | `doaj` | Fully open-access journals | none | when the journal deposits one |
| Europe PMC | `epmc` | Biomedical and life sciences | none | articles with a PMC ID |
| Cochrane | `cochrane` | Cochrane systematic reviews (via Europe PMC) | none | open-access reviews |
| OpenAlex | `oa` | All disciplines | none; email optional | best open-access location |
| BASE | `base` | Repositories: theses, reports, grey literature | none | open PDF records |
| CORE | `core` | Open-access full text from repositories | key required | CORE download link |
| NASA ADS | `ads` | Astronomy, astrophysics, planetary science, physics | key required | ADS gateway for open articles |
| IEEE Xplore | `ieee` | IEEE journals and conferences | key required | open-access articles |
| Zenodo | `zenodo` | Publications deposited on Zenodo | none; token optional | attached PDF |
| Crossref | `crossref` | Every DOI registered with Crossref | none; email optional | publisher-deposited links |
| DBLP | `dblp` | Computer science venues | none | when the electronic edition is a PDF |
| HAL | `hal` | French open archive | none | deposited file |
| PubMed | `pubmed` | Biomedical citations (MEDLINE) | none; key optional | articles with a PMC ID |
| PubMed Central | `pmc` | Free full-text biomedical articles | none; key optional | every result |
| bioRxiv / medRxiv | `rxiv` | Biology and medicine preprints | none | every result |
| PEDro | `pedro` | Physiotherapy trials, reviews, guidelines | fair-use opt-in | none |
| Scopus | `scopus` | All disciplines (Elsevier index) | API key or browser session | none |

"PDF links" is what the source itself returns. When a result has no PDF link, `mosaic get` and `--download` still
look for an open copy through Unpaywall: see [Downloads](./downloads).

Keys and switches live in `~/.config/mosaic/config.toml`, one `[sources.<name>]` table per source; the
[configuration guide](./configuration#api-keys) lists the `mosaic config` flag for each key. Turn a source off with
`mosaic config --disable-source NAME`, where NAME is the config name (`semantic_scholar`, `nasa_ads`, ...), not the
shorthand.

## Notes per source

### arXiv

Every arXiv result is open access with a PDF link, so `--oa-only` removes nothing. mosaic waits
`rate_limit_delay` seconds (default 1.0) between two arXiv requests. arXiv's own query syntax works through
`--raw-query`:

```bash
mosaic search "" --raw-query "ti:hall AND ti:thruster AND cat:physics.plasm-ph" --source arxiv
```

### Semantic Scholar

Without a key, requests share Semantic Scholar's public pool and often come back as HTTP 429 (rate limited); the
source then drops out of the search, visible with `--verbose`. A free key gives you a private quota: request it at
[semanticscholar.org/product/api](https://www.semanticscholar.org/product/api), then
`mosaic config --ss-key KEY`. The key also enables Semantic Scholar recommendations in
[`mosaic similar`](./similar).

### ScienceDirect and Scopus

Both are Elsevier services and both have two modes, chosen when the search starts:

- with an API key ([dev.elsevier.com](https://dev.elsevier.com), free), mosaic calls the Elsevier search APIs.
  ScienceDirect in API mode returns open-access articles only. Scopus returns partial metadata (title, first author,
  journal, year, DOI, citation count) unless you also set an institutional token, `mosaic config --scopus-inst-token`;
- without a key, with a valid saved session (`mosaic auth login`), mosaic searches the website in a headless
  browser and sees what your institution subscribes to;
- with neither, the source is skipped.

ScienceDirect takes its key from `mosaic config --elsevier-key`, Scopus from `--scopus-key`: one Elsevier key can be
set for both. Scopus never returns PDF links. Browser sessions: [Authenticated access](./authenticated-access).

### Springer: two sources

`sp` loads `link.springer.com/search` in a headless browser (the result pages are built by JavaScript), so it needs
the `browser` extra and an installed browser, and is skipped otherwise. It needs no login. `springer` calls the
Springer Nature Open Access API: open-access articles only, with a free key from
[dev.springernature.com](https://dev.springernature.com) (`mosaic config --springer-key`). Run both; duplicates
merge by DOI. To exclude the browser source: `mosaic config --disable-source springer`.

### Cochrane

Cochrane's APIs need OAuth credentials issued on request, and scripted access to cochranelibrary.com is blocked.
The `cochrane` source is a Europe PMC search restricted to the Cochrane Database of Systematic Reviews
(ISSN 1469-493X); results link to the review on cochranelibrary.com. Every Europe PMC filter works.

### OpenAlex and Crossref

Both work without credentials. When you set an Unpaywall email (`mosaic config --unpaywall-email`), mosaic sends it
to OpenAlex and Crossref too, which puts your requests in their "polite pool" with higher limits. OpenAlex stores
abstracts as inverted indexes; mosaic rebuilds the text. Many Crossref records have no abstract.

### CORE, NASA ADS, IEEE Xplore

Each needs a free key and is skipped without one:

| Source | Get a key | Set it | Free quota |
|---|---|---|---|
| CORE | [core.ac.uk/services/api](https://core.ac.uk/services/api) | `mosaic config --core-key KEY` | per CORE tier |
| NASA ADS | [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu/user/settings/token), Settings, API Token | `mosaic config --ads-key KEY` | 5 000 requests/day |
| IEEE Xplore | [developer.ieee.org](https://developer.ieee.org) | `mosaic config --ieee-key KEY` | 200 requests/day |

### Zenodo

mosaic asks Zenodo for publications only (`resource_type.type:publication`), leaving out datasets and software.
Every record is open access. A personal token (`mosaic config --zenodo-key`) raises the anonymous rate limit.

### DBLP

DBLP has no abstracts. Combine it with arXiv or Semantic Scholar for computer science: the same paper from two
sources merges into one record that keeps the abstract.

### PubMed and PubMed Central

Both use the NCBI E-utilities, two requests per search. PubMed's summaries carry no abstract, so pair it with
Europe PMC for abstracts. Every PubMed Central record has a PDF link. One NCBI key serves both:
`mosaic config --ncbi-key KEY` sets it for PubMed and PubMed Central and raises NCBI's limit from 3 to 10 requests
per second.

### bioRxiv / medRxiv

mosaic searches both servers through their website search, then fetches each preprint's metadata, abstract and PDF
link from `api.biorxiv.org`. Every result is open access.

### PEDro

PEDro's [fair-use policy](https://pedro.org.au/fair-use/) forbids automated bulk downloading, so the source stays
off until you accept it:

```bash
mosaic config --pedro-fair-use
```

mosaic then waits 3 seconds between PEDro requests (`--pedro-rate-limit-delay` to change it). A search result
carries the title, the study type (in the journal field) and the PEDro scale score; authors, year, DOI and
abstract need one more request per result, which `--pedro-fetch-details` enables (per search, or
`mosaic config --pedro-fetch-details` for every search). With details, a 25-result search makes about 25 extra
requests: about 75 seconds at the default delay.

```bash
mosaic search "chronic low back pain" --source pedro --field title --pedro-fetch-details
```

## Rate limits and quotas

The HTTP sources send their requests through a retry layer (`RetryTransport` in `mosaic/sources/base.py`); the
exceptions are the ScienceDirect and Scopus APIs, the browser-based sources and custom sources. When a server answers HTTP 429 (too many requests) or 503 (service
unavailable), mosaic waits and tries again, at most twice. The wait is the server's `Retry-After` header when it
sends one, otherwise 1 second and then 2. When the server asks for more than 10 seconds (a daily quota, for
example), mosaic does not wait: that source fails at once and the search goes on with the others.

A failed source is reported in one line with `--verbose`:

```
Warning: IEEE Xplore: API quota exhausted (HTTP 403); try again later or tomorrow
Warning: Semantic Scholar: rate limited (HTTP 429); retry in ~60s
Warning: CORE: access denied (HTTP 401); check the API key / credentials
```

An HTTP 401 or 403 whose body mentions a quota or rate limit reads "quota exhausted"; any other 401 or 403 reads
"access denied", which usually means a wrong or not yet active key (new Elsevier keys take a few minutes to
activate).

See also: [tutorial: narrowing the results](/tutorial/02-narrowing), [searching recipes](/cookbook/searching),
[configuration](./configuration), [custom sources](./custom-sources), [`mosaic search`](/reference/search).
