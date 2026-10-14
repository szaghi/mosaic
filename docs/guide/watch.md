---
title: Watch Searches
---

# Watch Searches

A watch is a saved search that you re-run later to see **only the papers it has not returned before**. Use it to follow a topic without re-reading the same results every time.

```bash
mosaic watch add "diffusion models" --name diffusion --source arxiv --year 2024-2026
mosaic watch run            # later: only what is new since the last run
```

## Add a watch

`mosaic watch add` takes the same filters as `mosaic search` (`--source`, `--year`, `--author`, `--journal`, `--field`, `--raw-query`, `--oa-only`, `--max`):

```bash
mosaic watch add "exercise for chronic low back pain" --name lbp --source cochrane
```

```
Watch 'lbp' saved — baseline of 25 paper(s) recorded.
```

Adding a watch runs it once and records the current results as the **baseline**, without listing them. The first `watch run`, including one from cron, then reports only papers published or indexed since you added it. To see the baseline itself, run the same `mosaic search`.

## Run watches

```bash
mosaic watch run                 # all watches
mosaic watch run lbp diffusion   # selected watches
mosaic watch run --download      # also download PDFs of the new papers
```

```
lbp — 2 new of 25 result(s)
 # Title                                                   Year  Source    ...
 1 Weight management for chronic low back pain             2026  Cochrane
 2 Digital interventions for chronic low back pain         2026  Cochrane
diffusion — nothing new (25 result(s))
```

Every result is also saved to the [cache](./cache), so new papers are immediately available to `mosaic cache list`, `mosaic index`, and `mosaic ask`.

### What counts as "new"

Each watch keeps its own history of the papers it has returned. A paper is new for a watch when **that watch** has never returned it, even if it is already in your cache from another search or a `mosaic get`. Clearing the cache (`mosaic cache clear`) does not reset watches.

The window is the top `--max` results per source. A paper that was outside it on an earlier run and later moves into it is reported as new at that point.

## List and remove

```bash
mosaic watch list
```

```
 Name   Query                                Source     Seen   Last run (UTC)
 lbp    exercise for chronic low back pain   cochrane     27   2026-10-14 08:31:05
```

```bash
mosaic watch remove lbp      # deletes the watch and its history
```

## Run on a schedule

MOSAIC has no daemon; use your system scheduler. `--json` gives machine-readable output:

```bash
# crontab -e: every Monday at 07:00, append new papers to a log
0 7 * * 1  mosaic watch run --json >> ~/mosaic-watch.jsonl 2>&1
```

```json
{
  "status": "ok",
  "watches": [
    {
      "name": "lbp",
      "query": "exercise for chronic low back pain",
      "total": 25,
      "new": [{"uid": "10.1002/14651858.cd016276", "title": "Weight management for chronic low back pain", "...": "..."}],
      "downloaded": 0,
      "errors": []
    }
  ]
}
```

A source that fails during a run (network error, [quota exhausted](./sources#rate-limits-and-quotas)) is listed in `errors`; papers it would have returned are reported as new on the next successful run.
