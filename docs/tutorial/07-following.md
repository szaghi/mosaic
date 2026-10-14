---
pageClass: tutorial-page
aside: false
title: 7. Following a field
---

# 7. Following a field

A keyword search finds what you know to ask for. Two commands find the rest: papers related to one you trust, and
the papers that appear after today.

## Papers like this one

Boeuf's 2017 tutorial on Hall thruster physics makes a good seed:

<<< @/examples/output/07/similar.txt{console}

`mosaic similar` takes a DOI (or `arxiv:<id>`) and asks OpenAlex for the works it relates to that paper by shared
concepts. With a Semantic Scholar API key (`mosaic config --ss-key`) it also asks Semantic Scholar for
recommendations, which usually adds more. The options of `search` apply: `--sort`, `--oa-only`, `--download`,
`--output`, `--json`.

## A saved search

`mosaic watch add` saves a search and records what it returns today as the baseline:

<<< @/examples/output/07/add.txt{console}

<<< @/examples/output/07/list.txt{console}

`mosaic watch run` repeats every watch, or the ones you name, and reports only the papers that watch has never
returned, even if another search already put them in the cache:

<<< @/examples/output/07/run.txt{console}

Run right after `add`, it finds nothing new. Run it daily from cron, and download what is new:

```bash
# crontab -e
0 7 * * *  mosaic watch run --download >> ~/watch.log 2>&1
```

`mosaic watch run --json` prints the new papers of each watch for a script or a notification;
`mosaic watch remove NAME` deletes a watch. `watch add` takes the options of `search`: `--source`, `--year`,
`--author`, `--journal`, `--field`, `--raw-query`, `--oa-only`, `--max`.

::: tip What you learned
`mosaic similar` from a seed paper; `mosaic watch add`, `list`, `run` and `remove` for searches that report what is
new. Reference: [`similar`](/reference/similar), [`watch`](/reference/watch); guides:
[Similar papers](/guide/similar), [Watches](/guide/watch).
:::

Next: [8. A local model](./08-local-model).
