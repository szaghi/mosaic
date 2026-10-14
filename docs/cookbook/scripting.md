---
title: Scripts and agents
---

# Scripts and agents

Recipes for driving mosaic from shell scripts, cron, an AI agent or a browser.

[[toc]]

## Results as JSON

```bash
mosaic search "hall thruster particle-in-cell" --max 10 --json > results.json
mosaic similar 10.1063/1.4972269 --json | jq '.count'
```

`--json` replaces the table with one JSON document on standard output; progress and warnings stay off it, so the
output parses as it is. `search` (live, `--cached` or `--semantic`) and `similar` support it, as does
`watch run`. Guide: [Agents and Claude Code](/guide/agent-workflows).

## Just the DOIs

```bash
mosaic search "hall thruster" --cached --json | jq -r '.papers[].doi // empty'
mosaic search "hall thruster" --cached --oa-only --json | jq -r '.papers[] | "\(.year)\t\(.doi)\t\(.title)"'
```

Papers without a DOI have `"doi": null`; `// empty` drops them. `--sort`, `--oa-only` and `--pdf-only` apply
before the JSON is written, with `--cached` and `--semantic` too.

## A file and the JSON in one run

```bash
mosaic search "hall thruster anomalous transport" --json --output refs.bib --output refs.csv | jq '.count'
```

`--output` writes its files and `--json` prints the document, from the same results.

## The JSON document

```json
{
  "status": "ok",
  "query": "hall thruster",
  "count": 2,
  "papers": [{"title": "...", "authors": ["..."], "year": 2023, "doi": "...", "uid": "doi:...", "...": "..."}],
  "errors": ["Semantic Scholar: rate limited (HTTP 429); try again later"]
}
```

`errors` lists the sources that failed; the others still answered. `similar` adds `seed` (the seed paper's
title), `--summarise` adds `summary`. Each paper carries every field of the cache record plus its `uid`. The
[JSON output](/guide/agent-workflows#json-output) section lists the fields.

## Give Claude Code the mosaic skill

```bash
mosaic skill install            # ./.claude/skills/mosaic/SKILL.md, this project only
mosaic skill install --global   # ~/.claude/skills/mosaic/SKILL.md, every project
mosaic skill show               # print the skill
```

The skill teaches Claude Code the commands, the source shorthands and the JSON shape, so you can ask in plain
words ("collect the open-access papers on Hall thruster erosion since 2020 into a BibTeX file") and let it run
mosaic. Guide: [the Claude Code skill](/guide/agent-workflows#the-claude-code-skill).

## The web interface

```bash
mosaic ui                                  # http://127.0.0.1:5555, opens your browser
mosaic ui --port 8080 --no-browser
```

The web UI needs the `ui` extra. It has no login: anyone who reaches the port controls your mosaic, your keys and
your files. Keep the default host `127.0.0.1`; `--host 0.0.0.0` exposes it to your network. Guide:
[Web UI](/guide/web-ui).

## Exit codes you can rely on

```bash
mosaic import ~/Downloads/*.pdf || echo "some files were not imported"
```

| Situation | Exit status |
|---|---|
| a search ran, even with no results or failed sources | 0 |
| unknown `--source` shorthand, bad `--year` or `--field` | 1 |
| `mosaic import`: any file not imported | 1 |
| `mosaic watch run NAME` with an unknown watch | 1 |
| `mosaic get`: no PDF found for the DOI, or any paper of a `--from` file failed | 1 |
| `--source` naming a source that is not active (disabled, missing key) | 1 |
| `mosaic index` failed (no embedding model, server error) | 1 |

A source that fails during a search is not an error: check `errors` in the JSON output.
