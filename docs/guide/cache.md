---
title: Cache Management
---

# Cache Management

Every paper mosaic shows you is saved in a local SQLite database, `~/.local/share/mosaic/cache.db`. The cache is
your library: you search it offline, export it, index it for [questions](./rag), and it remembers which PDFs you
downloaded. `mosaic cache` inspects and maintains it.

## Usage

```bash
mosaic cache stats                  # what is stored
mosaic cache list -n 20             # the newest papers
mosaic cache show 10.3390/aerospace10010044
mosaic cache verify                 # do the downloaded PDFs still exist?
mosaic cache clean                  # forget downloads whose files are gone
mosaic cache export library.bib     # everything, to a file
mosaic cache clear                  # wipe it (asks first)
mosaic search "thruster simulation" --cached   # search it, offline
```

## What gets cached

- every result of `mosaic search`, `mosaic similar` and `mosaic watch run`;
- the Crossref record of each DOI you `mosaic get` or `mosaic import` that was not cached yet;
- a download record per paper: the local file and its status (`ok`, or `error: <reason>`);
- every live search (`search` without `--cached` or `--semantic`, from the command line or the web UI), counted by
  `cache stats` as "Searches logged";
- the vector index and citation edges built by `mosaic index`.

Move the database with `mosaic config --db-path PATH`.

## Inspecting

<<< @/examples/output/03/stats.txt{console}

`cache list` shows the newest papers first; `--query` (`-q`) keeps those whose title or abstract contains every
word of the query, and `--offset` pages through the rest:

<<< @/examples/output/03/list.txt{console}

`cache show` takes a DOI, an arXiv ID or a full uid (`doi:...`, `arxiv:...`), and prints the whole record, plus the
local file and download status when the paper was downloaded or a download failed:

<<< @/examples/output/03/show.txt{console}

## Searching the cache

```bash
mosaic search "thruster simulation" --cached --sort year
mosaic search "electron transport" --cached --year 2020-2026 --author Boeuf --oa-only
mosaic search "" --cached --sort relevance          # the whole cache, ranked
```

`--cached` makes no network request. A paper matches when its title or abstract contains every word of the
query, in any order and case: "thruster simulation" finds "Particle simulation of a Hall thruster". An empty
query matches every paper. All the `search` filters, `--sort`, `--output` and `--download` apply.
`--downloaded-only` keeps the papers whose PDF you have.

`--semantic` searches the [vector index](./rag) by meaning instead of by words, once `mosaic index` has run.

## How records are merged

The same paper arrives from several sources: arXiv and Crossref, OpenAlex and Semantic Scholar. The cache keys
papers by uid (the DOI, else the arXiv ID, else the PII, else the title) and merges a new record into the stored
one field by field:

| Field | Rule |
|---|---|
| `abstract` | the longer one |
| `pdf_url` | the first one recorded is kept |
| `is_open_access` | true wins |
| `citation_count` | the higher one; unknown never replaces a number |
| `authors` | the longer list |
| `doi`, `arxiv_id`, `pii`, `journal`, `volume`, `issue`, `pages`, `url` | filled when empty, never overwritten |
| `title`, `year`, `source` | the first one recorded is kept |

A record only gains information from later searches.

### `--prefer-cache`

`mosaic search --prefer-cache` replaces a freshly fetched paper by its cached record when that record is rich:
it has an abstract, a year and at least one author. The table then shows the merged metadata of earlier runs
instead of what one source returned this time.

## Maintenance

### verify

```bash
mosaic cache verify
```

<<< @/examples/output/04/verify.txt{console}

For every download recorded as `ok`, `verify` checks that the file exists and starts with the PDF signature. A
"not a PDF" file is an HTML page (a bot check, a landing page) that versions before 1.6 saved under a `.pdf`
name; current versions reject those when downloading. The problems are listed with their uid and path.

### clean

`mosaic cache clean` deletes the download records that `verify` flags. It never deletes files or paper metadata:
the next `mosaic get` of those papers downloads them again.

### export

```bash
mosaic cache export library.bib
mosaic cache export thrusters.csv --query "hall thruster" --limit 100
```

The format follows the extension: `.bib`, `.ris`, `.csv`, `.json`, `.md` (a table) or `.markdown` (a section per
paper), as for `search --output`. See [Exporting](/tutorial/06-exporting).

### clear

`mosaic cache clear` deletes papers, download records, the search and export logs, the vector index and the
citation graph, after a confirmation (`--yes` skips it). Your PDF files and your [watches](./watch) stay.

See also: [tutorial: the local cache](/tutorial/03-cache), [recipes](/cookbook/maintenance),
[`mosaic cache`](/reference/cache), [Downloads](./downloads).
