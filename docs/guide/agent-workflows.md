---
title: Agent Workflows & Claude Code Skill
---

# Agent Workflows & Claude Code Skill

MOSAIC ships a bundled [Claude Code](https://claude.ai/claude-code) skill that gives any Claude
Code session expert knowledge of all mosaic commands, sources, filters, export formats, and JSON
scripting patterns. Once installed, the `/mosaic` slash command is available in every conversation
in that project (or globally, with `--global`).

All `search` and `similar` commands support a `--json` flag that emits a structured JSON envelope
to stdout — designed for piping, agent scripting, and CI pipelines.

---

## Installing the Claude Code skill

```bash
# Install into the current project's .claude/skills/ directory
mosaic skill install

# Install globally to ~/.claude/skills/ — available in all your projects
mosaic skill install --global

# Inspect the bundled skill content (useful for review or manual installation)
mosaic skill show
```

After installation, open a new Claude Code session. The `/mosaic` slash command will be available.

::: tip What the skill provides
The skill teaches Claude Code the full mosaic command surface: all flags, source shorthands, JSON
schemas, export formats, Zotero/Obsidian integration patterns, RAG commands, and ready-to-run
agent workflow templates. You can ask it to build a bibliography, search multiple topics in parallel,
or script a full literature review — and it will produce correct, working mosaic commands.
:::

---

## JSON output — `--json`

Add `--json` to `search` or `similar` to get a structured JSON object on stdout instead of the
rich terminal table. All rich output is suppressed; the result is pipe-friendly.

```bash
mosaic search "attention mechanism" --max 30 --oa-only --json
mosaic similar 10.48550/arXiv.1706.03762 --max 15 --json
```

Papers are still saved to the local cache, so `--cached` queries work immediately after.

`--json` and `--output` can be combined: the file is written *and* JSON is printed to stdout.

```bash
# Save to BibTeX and also get structured stdout output
mosaic search "FDTD methods" --json --output refs.bib
```

### JSON schema — search

```json
{
  "status": "ok",
  "query": "attention mechanism",
  "count": 3,
  "papers": [
    {
      "title": "Attention Is All You Need",
      "authors": ["Vaswani, Ashish", "Shazeer, Noam"],
      "year": 2017,
      "doi": "10.48550/arXiv.1706.03762",
      "arxiv_id": "1706.03762",
      "pii": null,
      "abstract": "The dominant sequence transduction models...",
      "journal": null,
      "volume": null,
      "issue": null,
      "pages": null,
      "pdf_url": "https://arxiv.org/pdf/1706.03762",
      "source": "arxiv",
      "is_open_access": true,
      "url": "https://arxiv.org/abs/1706.03762",
      "citation_count": 50000,
      "relevance_score": null,
      "uid": "10.48550/arxiv.1706.03762"
    }
  ],
  "errors": []
}
```

`status` is always `"ok"` (source-level warnings go into `errors[]`; a fatal failure exits with
code 1 before printing). `uid` is the cache deduplication key (DOI → arXiv ID → PII → title
slug). All fields are always present; unavailable values are `null`.

### JSON schema — similar

Same as above plus a `"seed"` key with the resolved seed paper title:

```json
{
  "status": "ok",
  "seed": "Attention Is All You Need",
  "query": "10.48550/arXiv.1706.03762",
  "count": 10,
  "papers": [...],
  "errors": []
}
```

---

## Scripting patterns

### Bash — filter with jq

```bash
# Extract all DOIs from an OA search
dois=$(mosaic search "graph neural networks" --max 30 --oa-only --json \
       | jq -r '.papers[].doi | select(. != null)')

# Count papers with a direct PDF link
mosaic search "diffusion models" --max 50 --json \
  | jq '[.papers[] | select(.pdf_url != null)] | length'

# Print title + year for the top 5 most-cited
mosaic search "transformer" --sort citations --max 20 --json \
  | jq -r '.papers[:5][] | "\(.year)  \(.title)"'
```

### Python — full bibliography pipeline

```python
import json, subprocess
from pathlib import Path

def mosaic(args: list[str]) -> dict:
    r = subprocess.run(["mosaic"] + args, capture_output=True, text=True, check=False)
    if r.returncode != 0 and not r.stdout.strip():
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout)

# ── 1. Search multiple related queries ──────────────────────────────────────
queries = [
    "transformer self-attention mechanism",
    "BERT language model pre-training",
    "GPT autoregressive language model",
]
all_papers: list[dict] = []
for q in queries:
    data = mosaic(["search", q, "--max", "15", "--oa-only", "--json"])
    all_papers.extend(data["papers"])

# ── 2. Deduplicate by uid ────────────────────────────────────────────────────
seen: set[str] = set()
unique: list[dict] = []
for p in all_papers:
    if p["uid"] not in seen:
        seen.add(p["uid"])
        unique.append(p)

# ── 3. Expand with similar papers from the most-cited seed ──────────────────
most_cited = max(unique, key=lambda p: p["citation_count"] or 0)
if most_cited.get("doi"):
    related = mosaic(["similar", most_cited["doi"], "--max", "10", "--json"])
    for p in related["papers"]:
        if p["uid"] not in seen:
            seen.add(p["uid"])
            unique.append(p)

print(f"Collected {len(unique)} unique papers")

# ── 4. Export the cache to BibTeX ────────────────────────────────────────────
# (all papers from steps 1–3 are already in the cache)
subprocess.run(["mosaic", "search", queries[0], "--cached", "--output", "bibliography.bib"])

# ── 5. Index and ask ─────────────────────────────────────────────────────────
subprocess.run(["mosaic", "index"])
subprocess.run([
    "mosaic", "ask",
    "Summarise the evolution of attention mechanisms",
    "--mode", "synthesis",
    "--output", "synthesis.md",
])
```

---

## Using `/mosaic` in Claude Code

Once the skill is installed, describe your bibliography goal in plain English and Claude Code will
construct and run the right mosaic commands for you.

**Example prompts:**

- *"Search for papers on discontinuous Galerkin methods, filter for OA only, sort by citations, and export to refs.bib"*
- *"Find 20 papers similar to 10.1016/j.jcp.2020.109935 and push them to my Zotero 'CFD' collection"*
- *"Build a synthesis report on FDTD time-domain schemes — use my cached papers, index them, then ask in synthesis mode"*
- *"Give me a JSON list of all papers in my cache from 2022–2024 on neural ODEs"*

Claude Code will translate these into mosaic commands, run them, parse the output, and iterate.

---

## CI / automation

`--json` output is designed to be consumed in CI pipelines. Exit code is 0 on success, 1 on fatal
failure. Source-level warnings (non-fatal) are surfaced in the `errors[]` array.

```yaml
# GitHub Actions example
- name: Build bibliography
  run: |
    mosaic search "${{ inputs.query }}" --max 50 --oa-only --json > papers.json
    count=$(jq '.count' papers.json)
    echo "Found $count papers"
    mosaic search "${{ inputs.query }}" --cached --output bibliography.bib
```
