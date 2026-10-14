---
pageClass: tutorial-page
aside: false
title: 3. The local cache
---

# 3. The local cache

Every paper a search returns goes into a SQLite database, `~/.local/share/mosaic/cache.db`. After the searches of
the first two chapters it already holds a small library:

<<< @/examples/output/03/stats.txt{console}

When a paper arrives again, from another source or another search, mosaic fills in what the stored record lacks:
it keeps the first PDF link it learned, the longer of the two abstracts, a citation count, and the open-access flag
if any source set it.

## Searching offline

`--cached` searches the database and nothing else: no network, no keys, an answer in a fraction of a second.

<<< @/examples/output/03/cached.txt{console}

The words of the query must all appear in the title or the abstract, in any order. The options of a live search
work on cached results too: filters, `--sort`, `--output`, `--download`.

## Browsing and reading a record

<<< @/examples/output/03/list.txt{console}

`mosaic cache list` pages through the cache, newest first: `-n` papers per page, `--offset` to move on, `-q` to
filter. `mosaic cache show` prints one record in full, given a DOI, an arXiv ID or a uid:

<<< @/examples/output/03/show.txt{console}

The PDF URL of this record is the MDPI article page, not a PDF. [Chapter 4](./04-pdfs) shows what happens when
you ask for it.

## Preferring what you have

A live search shows the records the sources return today. With `--prefer-cache`, a paper whose cached record is
complete (title, year, authors and abstract) is shown from the cache instead:

```bash
mosaic search "hall thruster particle-in-cell" --prefer-cache
```

Use it when earlier searches built richer records than a source returns now.

::: tip What you learned
The cache records every result; `--cached` searches it offline; `mosaic cache stats`, `list` and `show` inspect
it. Reference: [`cache`](/reference/cache), guide: [The cache](/guide/cache).
:::

Next: [4. Getting the PDFs](./04-pdfs).
