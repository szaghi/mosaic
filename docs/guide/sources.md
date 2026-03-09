---
title: Sources
---

# Sources

MOSAIC aggregates results from multiple bibliographic databases plus one PDF resolver.

```mermaid
flowchart TD
    Q([Your query]) --> A[arXiv]
    Q --> B[Semantic Scholar]
    Q --> C[ScienceDirect]
    Q --> SP[Springer Nature browser]
    Q --> SPN[Springer Nature API]
    Q --> D[DOAJ]
    Q --> E[Europe PMC]
    Q --> F[OpenAlex]
    Q --> G[BASE]
    Q --> H[CORE]
    Q --> N[NASA ADS]
    Q --> IEEE[IEEE Xplore]
    Q --> Z[Zenodo]
    Q --> CR[Crossref]
    Q --> DBLP[DBLP]
    A & B & C & SP & SPN & D & E & F & G & H & N & IEEE & Z & CR & DBLP --> I{Deduplicate\nby DOI}
    I --> J[Result table]
    J -->|download| K{Has pdf_url?}
    K -- yes --> L[(Local disk)]
    K -- no --> M[Unpaywall]
    M --> L
```

## arXiv

| Property | Value |
|----------|-------|
| Auth | None |
| Content | Preprints — physics, maths, CS, biology, economics |
| PDF | Always available (all arXiv papers are OA) |
| Rate limit | 3 s between requests, max 2 000/page, 30 000 total |
| Base URL | `https://export.arxiv.org/api/query` |

arXiv is the best source for recent preprints and CS/physics papers. Because everything on arXiv is open access, `--oa-only` has no effect on arXiv results.

**Search fields supported:** `all:`, `ti:` (title), `au:` (author), `abs:` (abstract), `cat:` (category), `jr:` (journal ref)

```bash
mosaic search "ti:attention au:vaswani" --source arxiv
```

## Semantic Scholar

| Property | Value |
|----------|-------|
| Auth | Optional API key |
| Content | 214 million papers across all disciplines |
| PDF | `openAccessPdf.url` when available |
| Rate limit | 1 000 req/s (shared, no key) · 1 req/s (dedicated, with key) |
| Base URL | `https://api.semanticscholar.org/graph/v1` |

Semantic Scholar is the broadest source. Its `openAccessPdf` field provides a direct PDF link whenever Semantic Scholar has indexed a legal copy. Set an API key in the config for a private rate-limit slot.

To obtain a key, go to [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api), scroll to **"Get API Key"**, fill in your name, email, and a brief use-case description. The key is issued automatically by email — usually within minutes, no institutional affiliation required. Apply it with `mosaic config --ss-key YOUR_KEY`.

## ScienceDirect

| Property | Value |
|----------|-------|
| Auth | API key **or** saved browser session |
| Content | Elsevier journals and books |
| PDF | Open-access articles (API mode); Unpaywall fallback (browser mode) |
| Rate limit | 20 000–50 000 req/week, 2–10 req/s (API) · browser-paced (session) |
| Base URL | `https://api.elsevier.com/content/search/sciencedirect` (API) · `https://www.sciencedirect.com/search` (browser) |

MOSAIC selects the access mode automatically:

- **API key configured** — uses the Elsevier Article Search API. Fast and reliable. By default only open-access content is returned; full-text access to subscribed content requires an institutional token or campus/VPN IP.
- **Browser session saved, no API key** — uses headless Firefox to search `sciencedirect.com` with your institutional credentials. Returns results from subscribed content. PDF download via the session is blocked by Cloudflare on the `/pdfft/` endpoint; Unpaywall is used as fallback.
- **Neither** — source is skipped entirely.

::: tip Setup
- API key: `mosaic config --elsevier-key YOUR_KEY` — register free at [dev.elsevier.com](https://dev.elsevier.com)
- Browser session: see [Authenticated Access → ScienceDirect](./authenticated-access#sciencedirect-elsevier)
:::

## Springer Nature (browser) — shorthand `sp`

| Property | Value |
|----------|-------|
| Auth | None (publicly accessible) |
| Content | Springer, Nature, and affiliated journals and book series |
| PDF | Via Unpaywall or browser session (institutional access) |
| Rate limit | Browser-paced — one page load per request |
| Base URL | `https://link.springer.com/search` |

Springer Nature's search results are fully JavaScript-rendered, so MOSAIC uses a headless Firefox browser to fetch them. No login or API key is needed — the search interface is publicly accessible.

The source activates automatically whenever Playwright is installed (`pip install 'mosaic-search[browser]'`). It is disabled if the `[browser]` extra is not available.

Supports `--field title` (searches the article title field natively), `--year`, `--max` (with automatic page-by-page navigation for `--max > 20`), and `--journal` (appended to the keyword query).

DOIs are extracted directly from the article URLs in the search results.

::: tip CLI shorthand
```bash
mosaic search "adaptive mesh refinement" --source sp --field title --year 2020-2025
```
:::

::: info PDF access
For open-access articles, Unpaywall resolves a direct PDF link. For
subscribed content, a saved Springer browser session is used as a download
fallback — see [Authenticated Access](./authenticated-access).
:::

## Springer Nature (API) — shorthand `springer`

| Property | Value |
|----------|-------|
| Auth | API key required (free — register at [dev.springernature.com](https://dev.springernature.com)) |
| Content | Open-access articles from Springer, Nature, and affiliated journals |
| PDF | Direct PDF link from the `url` array when deposited |
| Rate limit | 5 000 req/day (free tier) |
| Base URL | `https://api.springernature.com/openaccess/json` |

The official Springer Nature Open Access API returns only freely accessible articles and includes direct PDF links when the publisher has deposited them. This source is faster and more reliable than the browser source but requires a free API key and is limited to OA content.

Supports `--field title` (uses the native `title:` query prefix), `--year` (appended as `date:YYYY-YYYY`), and `--max` (capped at 100 per request). Author and journal filters are applied as post-processing.

Both Springer sources can be active simultaneously; results are deduplicated by DOI.

::: tip Setup
Register for a free API key at [dev.springernature.com](https://dev.springernature.com), then add it to the config:

```toml
# ~/.config/mosaic/config.toml
[sources.springer_api]
api_key = "YOUR_KEY"
```
:::

::: tip CLI shorthand
```bash
mosaic search "protein folding" --source springer --field title --year 2020-2025
```
:::

## DOAJ

| Property | Value |
|----------|-------|
| Auth | None |
| Content | 100 % open-access journals (8 million+ articles) |
| PDF | Link included when published by a DOAJ-indexed journal |
| Rate limit | 2 req/s |
| Base URL | `https://doaj.org/api/v3/search/articles` |

Every result from DOAJ is fully open access by definition. Good source for humanities and social sciences in addition to STEM.

## Europe PMC

| Property | Value |
|----------|-------|
| Auth | None |
| Content | 45 million biomedical and life-science articles |
| PDF | PMC full-text PDF for open-access articles |
| Rate limit | No documented hard limit |
| Base URL | `https://www.ebi.ac.uk/europepmc/webservices/rest/search` |

Europe PMC is the best source for biomedical literature. Open-access papers with a PubMed Central ID (PMCID) include a direct PDF link.

## OpenAlex

| Property | Value |
|----------|-------|
| Auth | None (email optional) |
| Content | 250 million+ works across all disciplines |
| PDF | `best_oa_location.pdf_url` when available |
| Rate limit | 100 000 req/day (anonymous) · higher with polite-pool email |
| Base URL | `https://api.openalex.org/works` |

OpenAlex is the broadest freely available bibliographic database, covering journals, conference papers, books, datasets, and preprints across all disciplines. It is the successor to Microsoft Academic Graph.

When you set an Unpaywall email in the config, MOSAIC reuses it as the OpenAlex [polite-pool](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication) identifier, which grants significantly higher rate limits.

Abstracts in OpenAlex are stored as inverted indices (due to publisher licensing). MOSAIC reconstructs them automatically into plain text.

::: tip CLI shorthand
```bash
mosaic search "transformer" --source oa
```
:::

## BASE (Bielefeld Academic Search Engine)

| Property | Value |
|----------|-------|
| Auth | None |
| Content | 300 million+ documents from 10 000+ content providers |
| PDF | Direct PDF link when source format is `application/pdf` and OA |
| Rate limit | No documented hard limit — use responsibly |
| Base URL | `https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi` |

BASE aggregates metadata from institutional repositories, open-access journals, and digital libraries worldwide. It is particularly strong for grey literature, theses, and documents not indexed by journal-centric databases.

Search queries support Lucene syntax. Filters for author (`dccreator`), journal (`dcsource`), and year (`dcyear`) are appended natively.

::: tip CLI shorthand
```bash
mosaic search "climate change" --source base
```
:::

## CORE

| Property | Value |
|----------|-------|
| Auth | API key required (free — register at [core.ac.uk/services/api](https://core.ac.uk/services/api)) |
| Content | 200 million+ OA full-text documents from 10 000+ repositories |
| PDF | `downloadUrl` field — CORE's recommended full-text link |
| Rate limit | Varies by tier; free academic key gives generous limits |
| Base URL | `https://api.core.ac.uk/v3/search/works` |

CORE aggregates open-access full text from institutional repositories, preprint servers, and OA journals worldwide. Unlike BASE, CORE focuses exclusively on OA content and always provides a `downloadUrl` pointing to the actual document — making it the most reliable source for direct PDF access.

Filters for author (`authors.name`), journal (`journals.title`), and year (`yearPublished`) are applied natively in the query.

::: warning API key required
CORE is disabled until you set an API key:
```bash
# Edit ~/.config/mosaic/config.toml
[sources.core]
api_key = "YOUR_FREE_KEY"
```
Register for a free key at [core.ac.uk/services/api](https://core.ac.uk/services/api).
:::

::: tip CLI shorthand
```bash
mosaic search "open access publishing" --source core
```
:::

## NASA ADS (Astrophysics Data System)

| Property | Value |
|----------|-------|
| Auth | API key required (free — register at [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu/user/settings/token)) |
| Content | 15 million+ records in astronomy, astrophysics, planetary science, physics, and geosciences |
| PDF | Via bibcode gateway link for open-access articles |
| Rate limit | 5 000 req/day |
| Base URL | `https://api.adsabs.harvard.edu/v1/search/query` |

NASA ADS is the definitive database for astronomy and astrophysics literature, operated by the Smithsonian Astrophysical Observatory under a NASA grant. It covers journal articles, conference proceedings, preprints, and grey literature with strong links to arXiv copies.

Open-access articles include a PDF URL constructed from the ADS bibcode (`link_gateway`). ArXiv IDs are extracted from the `identifier` field when present.

::: warning API key required
NASA ADS is disabled until you set an API token. Registration is free:

1. Sign in at [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu)
2. Go to **Settings → API Token** and generate a token
3. Add it to the config file:

```toml
# ~/.config/mosaic/config.toml
[sources.nasa_ads]
api_key = "YOUR_TOKEN"
```
:::

::: tip CLI shorthand
```bash
mosaic search "gravitational waves" --source ads
```
:::

## Zenodo

| Property | Value |
|----------|-------|
| Auth | None (access token optional) |
| Content | 3 M+ open research outputs — papers, datasets, software, posters, theses |
| PDF | Direct download link when a PDF file is attached to the record |
| Rate limit | 60 req/min (anonymous) · higher with access token |
| Base URL | `https://zenodo.org/api/records` |

Zenodo is CERN's open-access repository, hosting research outputs from CERN and EU-funded projects across all disciplines. Every record in Zenodo is open access by definition. It is particularly strong for datasets, software, grey literature, and research outputs that are not published in traditional journals.

Search results are limited to `resource_type.type=publication` to exclude datasets and software entries.

When a PDF file is attached to a record, MOSAIC extracts its direct download URL from the `files` array.

::: tip CLI shorthand
```bash
mosaic search "climate data" --source zenodo
```
:::

::: tip Optional access token
Anonymous requests are limited to 60 req/min. A free personal access token raises this limit:

1. Sign in at [zenodo.org](https://zenodo.org)
2. Go to **Settings → Applications → Personal access tokens** and create a token with `deposit:read` scope
3. Add it to the config file:

```toml
# ~/.config/mosaic/config.toml
[sources.zenodo]
api_key = "YOUR_TOKEN"
```
:::

## Crossref

| Property | Value |
|----------|-------|
| Auth | None (email optional) |
| Content | 150 M+ scholarly works — journal articles, conference papers, books, datasets |
| PDF | Direct PDF link when deposited by the publisher in the `link` array |
| Rate limit | 50 req/s with polite-pool email |
| Base URL | `https://api.crossref.org/works` |

Crossref is the primary DOI registration agency for scholarly publishing. Its REST API exposes rich metadata for works deposited by member publishers, including title, authors, publication date, abstract (when provided), journal name, and publisher-deposited PDF links. Abstract coverage varies widely by publisher; many records have no abstract at all.

Field scoping: `--field title` uses the `query.title` parameter; `--field abstract` uses `query.bibliographic` (the closest available equivalent). Year, author, and journal filters are applied as post-processing.

When you set an Unpaywall email in the config, MOSAIC reuses it as the Crossref polite-pool identifier — no separate key is needed.

::: tip CLI shorthand
```bash
mosaic search "transformer attention" --source crossref
```
:::

## IEEE Xplore

| Property | Value |
|----------|-------|
| Auth | API key required (free — register at [developer.ieee.org](https://developer.ieee.org)) |
| Content | 5 M+ IEEE journals, transactions, magazines, and conference proceedings |
| PDF | Direct `pdf_url` field for open-access articles |
| Rate limit | 200 req/day (free tier) |
| Base URL | `https://ieeexploreapi.ieee.org/api/v1/search/articles` |

IEEE Xplore is the primary source for electrical engineering, computer science, and electronics literature published by IEEE. It covers decades of IEEE Transactions, conference proceedings, and standards documents.

Supports `--field title` (uses the native `title:` query prefix), `--field abstract` (uses `abstract:` prefix), and `--year` (sent as native `start_year` / `end_year` parameters). Author and journal filters are applied as post-processing.

::: warning API key required
IEEE Xplore is disabled until you set an API key. Registration is free:

1. Sign up at [developer.ieee.org](https://developer.ieee.org)
2. Create an application to obtain an API key
3. Add it to the config file:

```toml
# ~/.config/mosaic/config.toml
[sources.ieee]
api_key = "YOUR_KEY"
```
:::

::: tip CLI shorthand
```bash
mosaic search "deep learning hardware" --source ieee --field title --year 2020-2025
```
:::

## DBLP

| Property | Value |
|----------|-------|
| Auth | None |
| Content | 6 M+ CS publications — journals, conferences, workshops |
| PDF | Via `ee` field when it links to arXiv or a direct PDF |
| Rate limit | No documented hard limit — use responsibly |
| Base URL | `https://dblp.org/search/publ/api` |

DBLP (Digital Bibliography & Library Project) is the reference bibliography for computer science, maintained by Schloss Dagstuhl. It covers all major CS venues including IEEE, ACM, Springer LNCS, and arXiv CS preprints. DBLP provides no abstracts — results include title, authors, venue, year, DOI, and an electronic edition link (`ee`) that often points to an arXiv copy or an open publisher page.

Field scoping: `--field title` appends a `$` to the query string (DBLP title-only search convention). Year, author, and journal filters are applied as post-processing only.

::: info No abstract field
DBLP does not expose abstracts through its search API. The `abstract` field is always `None` for DBLP results. For CS papers with abstracts, combine with arXiv or Semantic Scholar — duplicates are merged by DOI.
:::

::: tip CLI shorthand
```bash
mosaic search "graph neural networks" --source dblp --field title --year 2020-2024
```
:::

## Unpaywall (PDF resolver)

Unpaywall is not a search source — it is a resolver used during download. For any paper with a DOI but no known PDF URL, MOSAIC calls:

```
GET https://api.unpaywall.org/v2/{doi}?email=you@example.com
```

Unpaywall checks 50 000+ repositories (PubMed Central, institutional repos, author pages, preprint servers) and returns the `best_oa_location.url_for_pdf` if a legal copy exists.

::: tip
Set your email in the config to enable this fallback:
```bash
mosaic config --unpaywall-email you@example.com
```
:::
