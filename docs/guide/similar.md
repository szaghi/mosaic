---
title: Find Similar Papers
---

# Find Similar Papers

`mosaic similar` lists papers related to one you already know, from its DOI or arXiv ID: no query to write. Use it
to grow a reading list around a key paper.

## Usage

```bash
mosaic similar 10.1063/1.4972269
mosaic similar arxiv:2304.06563 --max 20 --sort citations
mosaic similar 10.1063/1.4972269 --oa-only --download
mosaic similar 10.1063/1.4972269 --output related.bib
```

The identifier is a bare DOI, a DOI with a `doi:` or `DOI:` prefix, or an arXiv ID with an `arxiv:` or `ARXIV:`
prefix. The results take the options of `mosaic search`: `--oa-only`, `--pdf-only`, `--sort`, `--output`,
`--download`, `--zotero`, `--obsidian`, `--json`.

## How it works

| Source | What it returns | Needs |
|---|---|---|
| OpenAlex | the paper's `related_works`, a list OpenAlex computes for each work | nothing: always queried |
| Semantic Scholar | its recommendations for the paper | a Semantic Scholar API key |

mosaic looks the paper up on OpenAlex, takes the first `--max` (default 10) of its related works and fetches
their metadata; the table's title line names the paper. With a Semantic Scholar key configured
(`mosaic config --ss-key KEY`, free at [semanticscholar.org](https://www.semanticscholar.org/product/api)), it
also asks Semantic Scholar for up to `--max` recommendations and merges the two lists by uid, keeping the richer
record. A paper that OpenAlex does not know is reported as `Paper not found` and the command exits with status 1.

`--max` is an upper bound: OpenAlex lists a limited number of related works per paper, and a related work it
cannot return is dropped. `--sort relevance` ranks the results against the seed paper's title.

The results are saved to the [cache](./cache) like those of a search, so `mosaic search --cached` and
`mosaic index` see them.

## Limits

- Related works reflect OpenAlex's topic model, not the paper's references: expect neighbours in the field, not
  a citation list. For citations, see the [citation graph](./citation-graph).
- Without a Semantic Scholar key, the list is OpenAlex's alone.

See also: [tutorial: following a field](/tutorial/07-following), [recipes](/cookbook/searching),
[`mosaic similar`](/reference/similar).
