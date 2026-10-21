---
title: Downloads
---

# Downloads

How mosaic finds a legal PDF for a paper, checks it, and files it in your library. The same downloader serves
`mosaic get`, `mosaic search --download`, `mosaic similar --download` and `mosaic watch run --download`.

## Usage

```bash
mosaic get 10.3389/fphy.2019.00140          # one paper, by DOI
mosaic get --from refs.bib                  # every DOI of a .bib or .csv file
mosaic search "hall thruster" --download    # the PDFs of a search
mosaic import ~/Downloads/paper.pdf         # a PDF you downloaded yourself
```

<<< @/examples/output/04/get.txt{console}

Set an e-mail address for Unpaywall once; without it mosaic skips the Unpaywall step:

```bash
mosaic config --unpaywall-email you@example.org
```

## How it works

For each paper, mosaic stops at the first step that yields a PDF:

1. **Already downloaded.** The cache records every download. If the paper has an `ok` record and the file is
   still a PDF, mosaic returns that file and downloads nothing.
2. **The source's PDF link.** Many sources (arXiv, DOAJ, Europe PMC, HAL, PubMed Central, ...) return a direct
   PDF URL with the search result.
3. **Unpaywall.** With a DOI and an e-mail address configured, mosaic asks
   [Unpaywall](https://unpaywall.org) for the open-access copies of the paper and tries them in order: the PDF
   link of every location, best first; then, for a copy in HAL, the record's `/document` URL; then the landing
   page of the best location. At most 6 candidates are tried. A publisher copy behind a bot wall often fails
   where the repository copy of the same paper succeeds.
4. **A saved browser session.** If you saved logins with `mosaic auth login`, mosaic opens the paper's page in
   a headless browser with your cookies, finds the PDF link and fetches it. The session whose domain matches the
   paper's page is tried; when none matches, every saved session is. See
   [Authenticated access](./authenticated-access).

When all steps fail, the cache records the failure and mosaic prints a hint:

<<< @/examples/output/04/blocked.txt{console}

### Only PDFs are saved

Publishers often answer a scripted request with HTTP 200 and an HTML page: a bot check, a cookie banner, the
abstract page. The status code proves nothing, so mosaic reads the first 1024 bytes of every response and keeps
it only if they contain the PDF signature `%PDF-`. Anything else is rejected as `not a pdf (<content type>)` and
the next candidate is tried.

The body is streamed to `<name>.pdf.part` and renamed to `<name>.pdf` only when complete: an interrupted or
rejected download never leaves a file under the final name.

### File names

Files go to `download_dir` (default `~/mosaic-papers`, or `--download-dir` for one run), named by
`filename_pattern`, default `{year}_{source}_{author}_{title}`:

| Placeholder | Value |
|---|---|
| `{year}` | publication year, `0000` when unknown |
| `{source}` | the source that returned the paper (`arXiv`, `DOAJ`, `Crossref`, ...) |
| `{author}` | the first word of the first author's name as the source lists it: the family name for "Family, Given" sources such as Crossref, the given name for "Given Family" sources such as arXiv |
| `{title}` | the title |
| `{journal}` | the journal, `no_journal` when unknown |
| `{doi}` | the DOI with `/` replaced by `_`, `no_doi` when unknown |

Each value is cut to 60 characters, punctuation is dropped and spaces become `_`. Change the pattern with
`mosaic config --filename-pattern "{year}_{author}_{title}"`.

`mosaic get DOI` and `mosaic get --from` look each DOI up in the cache, then on Crossref, so the file is named
after the paper's real year, author and title. If Crossref does not know the DOI, the download goes ahead with
the DOI as the title and `manual` as the source.

### Bulk downloads

`mosaic get --from FILE` reads the DOIs of a BibTeX file (every `doi = {...}` or `doi = "..."` field) or of a
CSV file with a `doi` column (any capitalisation). A DOI listed twice is downloaded once; entries without a DOI
are ignored.

<<< @/examples/output/04/bulk.txt{console}

With `--oa-only`, a paper without a downloadable copy counts as skipped, `– DOI (no OA copy)`, instead of
failed, and the retry hint is not shown.

## PDFs you downloaded yourself

`mosaic import FILE...` moves PDFs you already have into the library, named and recorded as if `mosaic get` had
downloaded them, so `mosaic cache verify` and `mosaic index` see them.

<<< @/examples/output/05/import.txt{console}

mosaic finds the paper's DOI in this order:

1. the document's own DOI in the PDF metadata (XMP or the Info dictionary), anywhere in the file;
2. the PII in a ScienceDirect download name, `1-s2.0-<PII>-main.pdf`, looked up on Crossref;
3. a DOI in the first 2 MB of the file, but only if exactly one distinct DOI appears there (a reference list
   cites many, so several mean "unknown").

When none applies, pass it: `mosaic import scan.pdf --doi 10.1016/j.paerosci.2006.01.001` (one file at a time).
Title, authors and year come from the cache or Crossref.

- A file that is not a PDF is refused and left where it is.
- If a PDF already has the target name, mosaic refuses unless you pass `--force`. An HTML page saved under that
  name (by versions before 1.6) is replaced.
- The original is copied, then deleted. If Windows keeps it locked (an antivirus scan, for example), the copy in
  the library stays and the original is left in place.
- `mosaic import` exits with status 1 if any file could not be imported.

## Checking the library

```bash
mosaic cache verify     # every recorded download: does the file exist, is it a PDF?
mosaic cache clean      # forget the records of missing and non-PDF files
```

<<< @/examples/output/04/verify.txt{console}

`cache clean` removes download records only, never files. The next `mosaic get` of those papers downloads them
again. See [Cache](./cache#verify).

## Limits and troubleshooting

- **No Unpaywall step.** Without `unpaywall.email` in the config, step 3 is skipped. Set it with
  `mosaic config --unpaywall-email`.
- **Open access, still not downloaded.** Some open-access publishers refuse every scripted client: MDPI, for one,
  answers HTTP 403 to mosaic and to `curl` alike. mosaic does not disguise itself to get past such walls. Use
  `mosaic get DOI --auto` (mosaic drives your Chrome through the same moves you would make) or
  `mosaic get DOI --handoff` (you click, mosaic files)
  ([authenticated access](./authenticated-access#auto-pass-with-your-chrome-auto)).
- **Paywalled papers.** If you have access through a subscription or your institution, see
  [Authenticated access](./authenticated-access): the `--auto` pass, saved sessions, `--interactive`,
  `--handoff`.
- **Why did a download fail?** The cache keeps the reason of the last failure: `mosaic cache show DOI` prints it
  as the download status, for example `error: not a pdf (text/html)`.

See also: [tutorial: getting the PDFs](/tutorial/04-pdfs), [paywalled papers](/tutorial/05-paywalls),
[recipes](/cookbook/downloading), [`mosaic get`](/reference/get), [`mosaic import`](/reference/import).
