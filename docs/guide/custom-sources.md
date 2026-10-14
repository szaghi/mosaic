---
title: Custom Sources
---

# Custom Sources

Any search API that answers JSON can become a mosaic source, with a block of TOML and no Python. Each
`[[custom_sources]]` block in `~/.config/mosaic/config.toml` is one source; every `mosaic search` queries it next
to the built-in sources, and its results are merged by DOI, filtered and shown in the same table.

## A first source

This block searches Zenodo's record API (Zenodo is also a built-in source; it is used here because you can check
the mapping against a public API):

```toml
[[custom_sources]]
name              = "Zenodo records"
url               = "https://zenodo.org/api/records"
query_param       = "q"
results_path      = "hits.hits"
max_results_param = "size"
authors_path      = "metadata.creators"
authors_field     = "name"

[custom_sources.fields]
title    = "metadata.title"
doi      = "doi"
year     = "metadata.publication_date"
abstract = "metadata.description"
journal  = "metadata.journal.title"
url      = "links.self_html"
```

`mosaic search "hall thruster"` then also sends `GET https://zenodo.org/api/records?q=hall+thruster&size=10` and
reads the papers from the `hits.hits` array of the answer.

::: warning Keys after a table header belong to that table
In TOML, every `key = value` after `[custom_sources.fields]` goes into `fields`. Put the source's own keys
(`authors_path`, `authors_field`, `api_key`, ...) above the `[custom_sources.fields]` line, as in the block above,
or mosaic does not see them.
:::

## Keys

Source keys, above `[custom_sources.fields]`:

| Key | Default | Meaning |
|---|---|---|
| `name` | required | Label in the Source column |
| `url` | required | Endpoint; the source is skipped while it is empty |
| `enabled` | `true` | `false` keeps the block but stops querying it |
| `method` | `"GET"` | `"GET"` sends the query as a URL parameter, `"POST"` as a JSON body |
| `query_param` | `"q"` | Parameter (GET) or body key (POST) that carries the query |
| `results_path` | `"results"` | Dot path to the array of results in the answer; empty: the answer is the array |
| `max_results_param` | `""` | Parameter or body key for the page size; mosaic sends `--max`, at most 100 |
| `api_key` | `""` | Sent in the header `api_key_header` when set |
| `api_key_header` | `"X-API-Key"` | Header name for the key |
| `authors_path` | `""` | Dot path to an array of author objects |
| `authors_field` | `""` | Key holding the name in each author object |

Field keys, in `[custom_sources.fields]`. Each value is a dot path inside one result (`metadata.journal.title`);
leave out what the API does not have:

| Field | Becomes | Notes |
|---|---|---|
| `title` | title | |
| `doi` | DOI | Used to merge with other sources |
| `year` | year | An integer, `"2023"` or a date such as `"2023-05-01"`: mosaic keeps the first four-digit number |
| `abstract` | abstract | |
| `journal` | journal | |
| `authors` | authors | Path to an array of strings; use `authors_path` and `authors_field` for objects |
| `pdf_url` | PDF link | Downloaded by `--download` |
| `url` | landing page | |
| `is_open_access` | open-access flag | Any true value |

## Filters

mosaic sends the query text, or the `--raw-query` text when you give one. `--field`, `--year`, `--author` and
`--journal` are not translated for a custom API: mosaic applies `--year`, `--author` and `--journal` to the
results afterwards, as it does for every source, and ignores `--field`. `--oa-only` and `--pdf-only` work on the
fields you mapped.

## Limits

- `--source` accepts the built-in shorthands only, so a custom source runs in full searches and cannot be
  searched alone.
- A custom source has no retry on HTTP 429 or 503, unlike the built-in HTTP sources: a rate-limited answer drops it
  from that search (`mosaic --verbose search ...` shows the error).
- There is no way to add fixed parameters to a GET request: a query string written in `url` is replaced by the
  query and page-size parameters. An API that returns only IDs unless told which fields to send back (HAL's
  `fl=`, for example) cannot be mapped.

See also: [sources](./sources), [configuration](./configuration), [searching recipes](/cookbook/searching).
