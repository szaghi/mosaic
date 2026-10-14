---
pageClass: tutorial-page
aside: false
title: 4. Getting the PDFs
---

# 4. Getting the PDFs

mosaic downloads what you can read legally for free, and what your own access opens
([chapter 5](./05-paywalls)). For papers whose source gave no PDF link it asks [Unpaywall](https://unpaywall.org),
which wants an e-mail address with every request. Set yours once:

```bash
mosaic config --unpaywall-email you@example.org
```

Without it, mosaic skips Unpaywall and says so when a download fails.

## While searching

<<< @/examples/output/04/download.txt{console}

`--download` (`-d`) fetches the PDF of every result shown, into `~/mosaic-papers/`. A paper downloaded before is
not fetched again: the cache remembers where it is. `--download-dir DIR` sends one run elsewhere;
`mosaic config --download-dir DIR` changes the default.

## One paper by DOI

<<< @/examples/output/04/get.txt{console}

`mosaic get` takes a DOI, bare, with a `doi:` prefix or as a `https://doi.org/` link; an arXiv paper has the DOI
`10.48550/arXiv.<id>`. mosaic looks for a PDF in this order and stops at the first file that really is a PDF:

1. the PDF link in the cache, if a search found one;
2. every open-access copy Unpaywall knows, best first: the publisher's, a repository such as arXiv, PubMed
   Central, HAL or a university archive;
3. a browser session you saved with `mosaic auth login` ([chapter 5](./05-paywalls)).

An open-access paper can still fail:

<<< @/examples/output/04/blocked.txt{console}

MDPI answers every scripted download with HTTP 403, an anti-bot wall, and no repository holds a copy of this
paper. mosaic does not try to get past such walls; the hint names the two ways that use your own browser.

## The library

<<< @/examples/output/04/ls.txt{console}

Files are named `{year}_{source}_{author}_{title}.pdf`. `{author}` is the first word of the first author's name
as the source wrote it: a given name from arXiv ("Maryam Reza"), a family name from Crossref ("Reza, Maryam").
Titles are cut to 60 characters. Change the pattern with `mosaic config --filename-pattern`; the placeholders are
`{year}`, `{source}`, `{author}`, `{title}`, `{journal}` and `{doi}`.

## A list of DOIs

Your reference manager exports BibTeX; mosaic reads the `doi` fields of a `.bib` file, or the `doi` column of a
`.csv`:

<<< @/examples/output/04/bulk.txt{console}

For each DOI mosaic takes the title, authors and year from the cache or from Crossref, so the files get the same
names as after a search. The first paper has no open copy anywhere; it waits for [chapter 5](./05-paywalls).

## Checking the library

<<< @/examples/output/04/verify.txt{console}

`mosaic cache verify` checks that every recorded download still exists and starts with the PDF signature. A web
page saved as `.pdf` (a login or bot-check page, written by versions before 1.6) counts as "not a PDF".
`mosaic cache clean` forgets those records, and the missing ones, so the next `get` tries again; it deletes no
file.

::: tip What you learned
`--download`, `mosaic get` with a DOI or a `.bib`/`.csv` file, where mosaic looks for a PDF, file names,
`cache verify` and `cache clean`. Reference: [`get`](/reference/get), guide: [Downloads](/guide/downloads).
:::

Next: [5. Paywalled papers](./05-paywalls).
