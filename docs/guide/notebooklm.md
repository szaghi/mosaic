---
title: NotebookLM
---

# NotebookLM

`mosaic notebook create` turns a search, or a folder of PDFs, into a
[Google NotebookLM](https://notebooklm.google.com/) notebook, and can queue NotebookLM's generated material
(audio overview, briefing, quiz, slides, ...) in the same command.

::: warning Unofficial client
mosaic drives NotebookLM through [notebooklm-py](https://github.com/teng-lin/notebooklm-py), an unofficial
client. Google can change the service without notice and break it.
:::

## Setup

Install the extra, the browser it signs in with, and sign in once:

```bash
pipx install 'mosaic-search[notebooklm]'      # or [all]; with pip: pip install 'mosaic-search[notebooklm]'
~/.local/share/pipx/venvs/mosaic-search/bin/playwright install chromium
~/.local/share/pipx/venvs/mosaic-search/bin/notebooklm login
```

`notebooklm login` opens Chromium for the Google sign-in and saves the session; later `mosaic notebook` runs reuse
it without a browser. Run it again when Google signs you out. (With pipx, `pipx inject --include-apps
mosaic-search "notebooklm-py[browser]"` puts the `notebooklm` command on your PATH.)

## Usage

From a search:

```bash
mosaic notebook create "Hall thrusters" --query "hall thruster anomalous transport" --oa-only --max 10
mosaic notebook create "Hall thrusters" --query "hall thruster" -y 2020-2025 --podcast --briefing
```

From PDFs you already have, for example your mosaic library:

```bash
mosaic notebook create "Hall thruster reading list" --from-dir ~/mosaic-papers --slide-deck
```

Give `--query` or `--from-dir`, not both. The search takes the filters of `mosaic search` (`--year`, `--author`,
`--journal`, `--field`, `--raw-query`, `--oa-only`, `--pdf-only`, `--max`). The command ends with the notebook's
link.

## Generated material

Each flag queues one NotebookLM artifact after the import; combine as many as you want. NotebookLM generates them
in the background: they appear in the notebook's Studio panel after a few minutes.

| Flag | NotebookLM artifact |
|---|---|
| `--podcast` | Audio Overview |
| `--video` | Video Overview |
| `--briefing` | Briefing Doc |
| `--study-guide` | Study Guide |
| `--quiz` | Quiz |
| `--flashcards` | Flashcards |
| `--infographic` | Infographic |
| `--slide-deck` | Slide Deck |
| `--data-table` | Data Table |
| `--mind-map` | Mind Map |

If no source could be added, mosaic queues nothing and lists the artifacts it skipped: NotebookLM cannot generate
from an empty notebook.

## How it works

With `--query`, mosaic searches the enabled sources, applies the filters, and tries to download each paper's PDF
as [`mosaic get`](/guide/downloads) does, into the download directory (`--download-dir` overrides it). It then
creates the notebook and adds each paper: the PDF file when the download succeeded, otherwise the paper's web page
(its `url`); a paper with neither is left out. With `--from-dir`, it uploads the directory's `*.pdf` files in
alphabetical order.

NotebookLM accepts at most 50 sources per notebook: mosaic adds the first 50 and ignores the rest. A source that
NotebookLM refuses is skipped silently; the count shows in the notebook itself.

See also: [`mosaic notebook`](/reference/notebook), [AI recipes](/cookbook/ai).
