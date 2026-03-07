---
title: Custom Sources
---

# Custom Sources

MOSAIC supports **any number of user-defined search sources** configured
entirely in `~/.config/mosaic/config.toml` — no Python required. Each
source is one `[[custom_sources]]` block. Any REST API that returns JSON
can be wired in as a first-class source alongside arXiv, Semantic Scholar,
and the other built-in sources, and all of them are queried in parallel
on every search.

## How it works

Each custom source is an entry in the `[[custom_sources]]` array inside
`config.toml`. MOSAIC reads the config on startup, instantiates a generic
HTTP client for each enabled entry, and fans out searches to it exactly
as it does for built-in sources. Results are deduplicated, filtered, and
displayed in the same results table.

## Minimal example

```toml
# ~/.config/mosaic/config.toml

[[custom_sources]]
name         = "My Repo"
enabled      = true
url          = "https://api.myrepo.org/search"
method       = "GET"
query_param  = "q"
results_path = "results"

[custom_sources.fields]
title    = "title"
doi      = "doi"
year     = "year"
abstract = "abstract"
authors  = "authors"     # dot-notation path to a flat string array
```

A search like `mosaic search "protein folding"` will now also query
`https://api.myrepo.org/search?q=protein+folding` and merge the results.

## Full config reference

```toml
[[custom_sources]]
# ── Identity ─────────────────────────────────────────────────────────────────
name    = "CNR Publications"   # display name; used as source label in results
enabled = true                 # set false to disable without removing the entry

# ── Request ──────────────────────────────────────────────────────────────────
url          = "https://publications.cnr.it/api/search"
method       = "GET"           # "GET" (default) or "POST"
query_param  = "q"             # param/body key for the search string
results_path = "results"       # dot-notation path to the results array
                               # e.g. "data.items" for {"data":{"items":[…]}}

# ── Authentication (optional) ─────────────────────────────────────────────────
api_key        = ""            # API key value
api_key_header = "X-API-Key"   # HTTP header name for the key

# ── Pagination (optional) ─────────────────────────────────────────────────────
max_results_param = "limit"    # param/body key for the page size; omit if not needed

# ── Field mapping ─────────────────────────────────────────────────────────────
# Each value is a dot-notation path within a result object.
# Omit keys that the API does not provide.
[custom_sources.fields]
title          = "title"
doi            = "doi"
year           = "year"           # int, string year, or ISO date ("2023-05-01")
abstract       = "abstract"
journal        = "source.title"   # nested path supported
pdf_url        = "links.pdf"
url            = "links.html"
is_open_access = "openAccess"     # truthy value → Paper.is_open_access = True

# ── Authors ───────────────────────────────────────────────────────────────────
# Option A — flat string array ["Alice Smith", "Bob Jones"]:
# put the path inside [fields] as shown above.

# Option B — array of objects [{"name":"Alice"},{"name":"Bob"}]:
# use authors_path + authors_field at the top level (outside [fields])
authors_path  = "contributors"
authors_field = "name"
```

## Config key reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | str | *(required)* | Display name shown in results and used with `--source` |
| `enabled` | bool | `true` | Set `false` to disable without deleting the entry |
| `url` | str | *(required)* | Full API endpoint URL |
| `method` | str | `"GET"` | HTTP method: `"GET"` or `"POST"` |
| `query_param` | str | `"q"` | URL param (GET) or JSON body key (POST) for the query |
| `results_path` | str | `"results"` | Dot-notation path to the results array in the response |
| `api_key` | str | `""` | API key value (omit or leave empty if not needed) |
| `api_key_header` | str | `"X-API-Key"` | HTTP header used to send the API key |
| `max_results_param` | str | `""` | Param/body key for page size; omit if not supported |
| `[fields]` | table | `{}` | Dot-notation field mappings (see below) |
| `authors` | str | `""` | Dot-notation path to a flat string array of author names |
| `authors_path` | str | `""` | Path to array of author objects (use with `authors_field`) |
| `authors_field` | str | `""` | Key within each author object that holds the name |

### Field mapping paths

Paths use dot notation to navigate nested JSON:

| Field key | Maps to | Notes |
|-----------|---------|-------|
| `title` | `Paper.title` | |
| `doi` | `Paper.doi` | |
| `year` | `Paper.year` | Accepts int, `"2023"`, or `"2023-05-01"` |
| `abstract` | `Paper.abstract` | |
| `journal` | `Paper.journal` | |
| `pdf_url` | `Paper.pdf_url` | Used for direct PDF download |
| `url` | `Paper.url` | Landing page URL |
| `is_open_access` | `Paper.is_open_access` | Any truthy value works |

## Filtering behaviour

Custom sources are treated the same as built-in sources for post-processing
filters (`--year`, `--author`, `--journal`, `--oa-only`, `--pdf-only`).

Query-level filters (`--field title`, `--raw-query`) are applied as follows:

- **`--raw-query TEXT`** — sent verbatim as the query string instead of the
  user's query; useful for sources with native query syntax.
- **`--field title` / `--field abstract`** — *not* translated at the API
  level (custom sources have no knowledge of each API's field syntax);
  post-processing still applies.

## Selecting a custom source

Use the source's `name` exactly as defined in config:

```bash
mosaic search "neural networks" --source "CNR Publications"
```

## Multiple custom sources

Add as many `[[custom_sources]]` blocks as needed — each is an independent
source queried in parallel with all others. Here is a realistic two-source
example combining a generic institutional repository with a domain-specific
preprint server:

```toml
# ~/.config/mosaic/config.toml

# ── Source 1: HAL — French open archive (CNRS, INRIA, …) ─────────────────
[[custom_sources]]
name              = "HAL"
enabled           = true
url               = "https://api.archives-ouvertes.fr/search/"
method            = "GET"
query_param       = "q"
results_path      = "response.docs"
max_results_param = "rows"

[custom_sources.fields]
title    = "title_s"
doi      = "doiId_s"
year     = "publicationDateY_i"
abstract = "abstract_s"
journal  = "journalTitle_s"
url      = "uri_s"
pdf_url  = "fileMain_s"
authors  = "authFullName_s"        # HAL returns a flat string array of author names

# ── Source 2: ZENODO — general-purpose open research repository ───────────
[[custom_sources]]
name              = "Zenodo"
enabled           = true
url               = "https://zenodo.org/api/records"
method            = "GET"
query_param       = "q"
results_path      = "hits.hits"
max_results_param = "size"

[custom_sources.fields]
title    = "metadata.title"
doi      = "doi"
year     = "metadata.publication_date"   # ISO date → year extracted automatically
abstract = "metadata.description"
journal  = "metadata.journal.title"
url      = "links.self"
pdf_url  = "links.files"                 # first file link when present

authors_path  = "metadata.creators"
authors_field = "name"
```

With this config, `mosaic search "climate model"` queries arXiv, Semantic
Scholar, DOAJ, Europe PMC, OpenAlex, BASE, CORE, HAL, and Zenodo
simultaneously, then deduplicates all results by DOI.

To search only your custom sources:

```bash
mosaic search "climate model" --source HAL
mosaic search "climate model" --source Zenodo
```

To temporarily disable one without deleting its config, set `enabled = false`:

```toml
[[custom_sources]]
name    = "Zenodo"
enabled = false
# … rest of config unchanged
```

## Worked example — CNR IRIS via OAI-REST

If CNR exposes a JSON search endpoint (once you discover the URL), the
config would look like:

```toml
[[custom_sources]]
name         = "CNR Publications"
enabled      = true
url          = "https://publications.cnr.it/api/v2/search"
method       = "GET"
query_param  = "query"
results_path = "data.publications"
max_results_param = "size"

[custom_sources.fields]
title    = "title"
doi      = "doi"
year     = "year"
abstract = "abstract"
url      = "url"

authors_path  = "authors"
authors_field = "fullName"
```

No Python, no code changes — just save the file and run `mosaic search`.
