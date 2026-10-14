---
title: Watch Searches
---

# Watch Searches

A watch is a saved search that reports only the papers it has not returned before. Use one to follow a topic
without re-reading the same results.

## Usage

```bash
mosaic watch add "hall thruster anomalous transport" --name hall-transport --source arxiv
mosaic watch list
mosaic watch run                     # every watch
mosaic watch run hall-transport      # one of them
mosaic watch run --download          # and download the new papers' PDFs
mosaic watch remove hall-transport
```

### Adding a watch

`mosaic watch add QUERY --name NAME` takes the filters of `mosaic search`: `--source`, `--year`, `--author`,
`--journal`, `--field`, `--raw-query`, `--oa-only`, and `--max` (`-m`, default 25 results per source; `-n` is
the name).

<<< @/examples/output/07/add.txt{console}

Adding a watch runs it once and records the results as its baseline, without listing them, so the first
`watch run` reports only what appeared since. To read the baseline, run the same `mosaic search`. The watch is
checked when you add it: an unknown source, a bad year filter or an inactive source (a missing API key) is an
error and nothing is saved.

### Running watches

<<< @/examples/output/07/run.txt{console}

When a watch finds new papers, mosaic prints `NAME — N new of M result(s)` and the usual results table of the new
papers only. Every result, new or not, is saved to the [cache](./cache), so new papers are available to
`mosaic cache list`, `mosaic index` and `mosaic ask` at once.

<<< @/examples/output/07/list.txt{console}

Seen is the number of papers the watch has returned so far; Last run is in UTC.

## How it works

A watch stores the search as you typed it (query, source shorthand, filters) and rebuilds the filters at every
run, so it behaves as the equivalent `mosaic search` does with the config of the day.

Each watch keeps its own set of the uids it has returned. A paper is new for a watch when that watch never
returned it, even if the paper is already in your cache from another search or a `mosaic get`. Clearing the
cache does not reset watches; `mosaic watch remove` deletes a watch and its history.

The window is the first `--max` results per source. A paper outside the window on one run that enters it later is
reported as new then.

## On a schedule

mosaic has no daemon: use cron, a systemd timer or the Windows Task Scheduler. `--json` prints one JSON document
for all the watches run:

```bash
# crontab -e: every Monday at 07:00
0 7 * * 1  mosaic watch run --json >> ~/mosaic-watch.jsonl 2>&1
```

The document is `{"status": "ok", "watches": [...]}`; each watch has `name`, `query`, `total`, `new` (the new
papers, with every metadata field and their `uid`), `downloaded` (PDFs fetched with `--download`) and `errors`.
A watch that cannot run (its source has become inactive) has an `error` field instead. To list the titles:

```bash
mosaic watch run --json | jq -r '.watches[] | .name as $w | .new[] | "\($w)  \(.year)  \(.title)"'
```

A source that fails during a run (a network error, an exhausted [quota](./sources#rate-limits-and-quotas))
appears in `errors`; the papers it would have returned are reported as new on its next successful run.

See also: [tutorial: following a field](/tutorial/07-following), [recipes](/cookbook/monitoring),
[`mosaic watch`](/reference/watch).
