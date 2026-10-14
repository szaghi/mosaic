---
title: Keeping up
---

# Keeping up

Recipes for following a field after the first search: saved searches that report what is new, and papers related
to one you already trust.

[[toc]]

## Save a search

```bash
mosaic watch add "hall thruster anomalous transport" --name hall-transport
mosaic watch add "hall thruster" --name hall-arxiv --source arxiv --field title --year 2024-2026
```

`--name` is required and unique. The options are those of `search`: `--source`, `--year`, `--author`, `--journal`,
`--field`, `--raw-query`, `--oa-only`, and `--max` (`-m`, 25 per source by default). The papers the search returns
today become the baseline, so the first run reports nothing.
Tutorial: [following a field](/tutorial/07-following); guide: [Watches](/guide/watch).

## Check every watch

```bash
mosaic watch run                    # all watches
mosaic watch run hall-transport     # only the ones you name
mosaic watch list                   # name, query, papers seen, last run
```

A paper is new when this watch has never returned it, even if another search already put it in the cache. An
unknown watch name exits with status 1.

## Run it every morning

```bash
# crontab -e
0 7 * * *  mosaic watch run --download >> ~/watch.log 2>&1
```

`--download` (`-d`) fetches the PDFs of the new papers, as `mosaic get` would: set
`mosaic config --unpaywall-email` first, or open copies are not looked up.

## New papers as JSON, for a notification

```bash
mosaic watch run --json | jq -r '.watches[] | "\(.name): \(.new | length) new"'
```

The document is `{"status": "ok", "watches": [...]}`; each watch has `name`, `query`, `total`, `new` (the new papers,
with all their fields and `uid`), `downloaded` and `errors`. A watch whose source needs a missing key carries an
`error` field instead. [Agents and Claude Code](/guide/agent-workflows#watch-run) has the full shape.

## Papers related to one you like

```bash
mosaic similar 10.1063/1.4972269
mosaic similar arxiv:2304.06563 --max 25 --sort citations --oa-only
mosaic similar 10.1063/1.4972269 --output related.bib
```

`similar` takes a DOI or `arxiv:<id>` and returns the works OpenAlex relates to it. `--sort`, `--oa-only`,
`--pdf-only`, `--download`, `--output`, `--json`, `--zotero` and `--obsidian` behave as in `search`.
Guide: [Similar papers](/guide/similar).

## More related papers, with a Semantic Scholar key

```bash
mosaic config --ss-key YOUR_KEY
mosaic similar 10.1063/1.4972269
```

With a key, `similar` also asks Semantic Scholar's recommendation service and merges both lists. The key is free
from Semantic Scholar and also lifts the shared rate limit of the search source.

## Remove a watch

```bash
mosaic watch remove hall-arxiv
```

The watch and its list of seen papers are deleted; the papers stay in the cache.
