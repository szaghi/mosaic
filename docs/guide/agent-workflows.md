---
title: Agents and scripts
---

# Agents and scripts

Two things make mosaic easy to drive from a script or an AI agent: `--json`, which prints results as one JSON
object on standard output, and a bundled [Claude Code](https://claude.com/claude-code) skill that teaches Claude
Code every mosaic command.

## JSON output

`--json` replaces the table with a JSON object on `search`, `similar` and `watch run`. Nothing else is printed to
standard output, so you can pipe it:

```bash
mosaic search "hall thruster particle-in-cell" --cached --json | jq -r '.papers[] | "\(.year)  \(.doi)"' | head -n 5
mosaic similar 10.1063/1.4972269 --max 15 --json
mosaic watch run --json
```

The papers are saved to the cache as usual, and on a live search `--output` still writes its files:

```bash
mosaic search "hall thruster" --max 20 --json --output refs.bib > papers.json
```

### search and similar

A real envelope (one paper shown, abstract shortened):

```json
{
  "status": "ok",
  "query": "Effects of the neutral dynamics model",
  "count": 2,
  "papers": [
    {
      "title": "Effects of the neutral dynamics model on the particle-in-cell simulations of a Hall thruster plasma discharge",
      "authors": ["Farbod Faraji", "Maryam Reza", "Aaron Knoll"],
      "year": 2023,
      "doi": "10.1063/5.0143292",
      "arxiv_id": "2304.00585v1",
      "pii": null,
      "abstract": "The dynamics of the neutral atoms in Hall thrusters affect several plasma processes, ...",
      "journal": "Journal of Applied Physics 133, 213301 (2023)",
      "volume": null,
      "issue": null,
      "pages": null,
      "pdf_url": "https://arxiv.org/pdf/2304.00585v1",
      "source": "arXiv",
      "is_open_access": true,
      "url": "https://arxiv.org/abs/2304.00585v1",
      "citation_count": null,
      "relevance_score": null,
      "openalex_id": null,
      "uid": "doi:10.1063/5.0143292"
    }
  ],
  "errors": []
}
```

- Every paper has every field; a missing value is `null`. `relevance_score` is set by `--sort relevance`.
- `uid` is the key mosaic deduplicates and caches by: `doi:<doi>`, `arxiv:<id>`, `pii:<pii>` or `title:<title>`,
  the first that exists (arXiv DOIs `10.48550/arXiv.N` become `arxiv:N`).
- On a live `search`, `errors` lists the sources that failed (rate limits, timeouts) on a run that still produced
  results.
- `similar` adds `"seed"`: the title of the paper you started from. If the identifier is not found, it prints
  `{"status": "error", "query": ..., "errors": ["Paper not found"]}` and exits with code 1.
- With `--summarise`, `search` adds `"summary"`: the paragraph, whose `[n]` refers to the n-th entry of `papers`,
  or `null` when no summary could be made (the reason is in `errors`). See
  [tutorial chapter 8](/tutorial/08-local-model).

Other failures (an unknown `--source`, a bad `--year`) print a message, not JSON, and exit with code 1. Test the
exit code before parsing.

### watch run

```json
{
  "status": "ok",
  "watches": [
    {"name": "hall-transport", "query": "hall thruster anomalous transport", "total": 25,
     "new": [], "downloaded": 0, "errors": []}
  ]
}
```

`new` holds the papers not seen by earlier runs, in the format above. See [watches](/guide/watch).

## Patterns

```bash
# DOIs of the open-access results
mosaic search "hall thruster anomalous transport" --max 30 --oa-only --json | jq -r '.papers[].doi | select(. != null)'

# how many results have a PDF link
mosaic search "hall thruster" --max 50 --json | jq '[.papers[] | select(.pdf_url != null)] | length'

# the five most cited
mosaic search "hall thruster" --sort citations --max 20 --json | jq -r '.papers[:5][] | "\(.citation_count)  \(.title)"'
```

From Python, call the command and parse its output:

```python
import json
import subprocess


def mosaic(*args: str) -> dict:
    run = subprocess.run(["mosaic", *args, "--json"], capture_output=True, text=True, check=False)
    if run.returncode != 0:
        raise RuntimeError(run.stdout + run.stderr)
    return json.loads(run.stdout)


seen = {}
for query in ("hall thruster anomalous transport", "hall thruster particle-in-cell"):
    for paper in mosaic("search", query, "--max", "15", "--oa-only")["papers"]:
        seen[paper["uid"]] = paper
print(len(seen), "papers")
```

Every paper of both searches is now in the cache: `mosaic search "hall thruster" --cached --output refs.bib` writes
them to BibTeX, and `mosaic index` makes them searchable by meaning.

## The Claude Code skill

```bash
mosaic skill install            # into ./.claude/skills/mosaic/SKILL.md, for this project
mosaic skill install --global   # into ~/.claude/skills/mosaic/SKILL.md, for every project
mosaic skill show               # print the skill
```

Start a new Claude Code session after installing: the skill is available as `/mosaic`, and Claude Code also loads it
by itself when you ask for literature work. The skill describes the commands, the source shorthands, the filters,
the export formats, the JSON envelope and the integrations, so Claude Code writes valid mosaic commands, runs them
and reads their JSON. Requests it handles:

- "Find open-access papers on Hall thruster anomalous transport since 2020, sorted by citations, and write refs.bib."
- "Add the 20 papers most similar to 10.1063/1.4972269 to my Zotero collection 'Hall thrusters'."
- "Index my cached papers and tell me what they say about electron-wall interaction, with sources."

The skill is a copy: after upgrading mosaic, run `mosaic skill install` again to update it.

See also: [scripting recipes](/cookbook/scripting), [`mosaic search`](/reference/search),
[`mosaic skill`](/reference/skill).
