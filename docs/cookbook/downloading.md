---
title: Downloading
---

# Downloading

Recipes for getting the PDFs of open-access papers into your library, one at a time or from a list.

[[toc]]

## Set the Unpaywall e-mail

```bash
mosaic config --unpaywall-email you@example.org
```

Unpaywall finds the legal open copies of a paper (publisher, arXiv, PubMed Central, institutional repositories)
and wants an e-mail address with each request. Without one, mosaic does not ask it: a failed download then ends
with a line saying so.
Tutorial: [getting the PDFs](/tutorial/04-pdfs). Guide: [Downloads](/guide/downloads).

## The results of a search

```bash
mosaic search "hall thruster particle-in-cell" --source arxiv --download
mosaic search "thruster simulation" --cached --oa-only -d
```

`--download` (`-d`) fetches the PDF of every paper in the table, into `~/mosaic-papers/`. Papers downloaded before
are not fetched again.

## One paper by DOI

```bash
mosaic get 10.3389/fphy.2019.00140
mosaic get doi:10.3389/fphy.2019.00140
mosaic get https://doi.org/10.3389/fphy.2019.00140
mosaic get 10.48550/arXiv.2304.06563          # an arXiv paper
```

mosaic tries the PDF link from the cache, then every copy Unpaywall lists, then your saved browser sessions, and
keeps the first file that starts with the PDF signature. The file is named from Crossref's metadata.
Guide: [how it works](/guide/downloads#how-it-works).

## A BibTeX or CSV file of DOIs

```bash
mosaic get --from refs.bib
mosaic get --from papers.csv --oa-only
```

mosaic reads the `doi` fields of a `.bib` file, or the `doi` column of a `.csv` (header in any case), and downloads
each DOI once. The summary counts downloaded, failed and skipped papers; with `--oa-only`, a paper with no open copy
counts as skipped instead of failed, and the hint about `--handoff` is not printed.
Tutorial: [a list of DOIs](/tutorial/04-pdfs#a-list-of-dois).

## A folder per project

```bash
mosaic get --from refs.bib --download-dir ~/papers/hall-thrusters     # this run
mosaic config --download-dir ~/papers                                 # the default
```

`--download-dir` exists on `search`, `similar`, `get` and `import`. The cache records where each file went, so
`mosaic cache verify` checks all your folders.

## Other file names

```bash
mosaic config --filename-pattern "{year}_{author}_{title}"
mosaic config --filename-pattern "{journal}_{year}_{author}_{title}"
```

The placeholders are `{year}`, `{source}`, `{author}`, `{title}`, `{journal}` and `{doi}`; the default is
`{year}_{source}_{author}_{title}`. `{author}` is the first word of the first author's name as the source wrote
it: a given name from arXiv ("Maryam Reza"), a family name from Crossref ("Reza, Maryam"). Titles are cut to 60
characters, and characters other than letters, digits, `-`, `_` and `.` are dropped, `/` included: a pattern
cannot create subfolders. The pattern applies to new downloads; files already in the library keep their names.
Guide: [file names](/guide/downloads#file-names).

## Only the papers with a PDF link

```bash
mosaic search "hall thruster anomalous transport" --pdf-only --download
```

`--pdf-only` keeps the papers whose source gave a PDF link, so every download in the run is a direct fetch with no
Unpaywall lookup.

## Find and forget files that are not PDFs

```bash
mosaic cache verify
mosaic cache clean
```

`verify` checks that each recorded download exists and starts with `%PDF-`. Versions before 1.6 sometimes saved a
login or bot-check page as `.pdf`; `clean` forgets those records and the ones whose file is missing, so the next
`get` tries again. It deletes no file.
Guide: [checking the library](/guide/downloads#checking-the-library).

## A publisher answers 403

<<< @/examples/output/04/blocked.txt{console}

Some publishers, MDPI among them, refuse every scripted download with HTTP 403, even for open-access papers.
mosaic does not get around that. Download it in your browser and let mosaic file it:

```bash
mosaic get 10.3390/aerospace10010044 --handoff
```

Recipes: [Paywalled papers](./paywalls).
