---
title: NotebookLM Integration
---

# NotebookLM Integration

MOSAIC can create and populate [Google NotebookLM](https://notebooklm.google.com/) notebooks directly from search results. After finding and downloading open-access PDFs, MOSAIC imports them into a new notebook — ready for AI-powered Q&A, summaries, quizzes, and audio overviews.

::: warning Unofficial integration
This feature uses [notebooklm-py](https://github.com/teng-lin/notebooklm-py), an unofficial Python client for NotebookLM. Google may change internal APIs without notice. Use for personal projects and research.
:::

## Setup

### 1. Inject notebooklm-py into MOSAIC

`--include-apps` exposes the `notebooklm` CLI to your PATH. `[browser]` pulls in Playwright, which is needed for the one-time Google sign-in.

```bash
# pipx
pipx inject --include-apps mosaic-search "notebooklm-py[browser]"

# uv
uv tool inject --include-apps mosaic-search "notebooklm-py[browser]"

# pip / venv (activate your venv first)
pip install "notebooklm-py[browser]"
```

### 2. Install the Chromium browser (one-time)

Playwright is installed inside the MOSAIC tool venv but its own CLI is not exposed to PATH by pipx/uv. Download the Chromium binary by calling it directly from the venv:

```bash
# pipx
~/.local/share/pipx/venvs/mosaic-search/bin/playwright install chromium

# uv
~/.local/share/uv/tools/mosaic-search/bin/playwright install chromium

# pip / venv (playwright is on PATH inside the activated venv)
playwright install chromium
```

This is a ~150 MB one-time download to `~/.cache/ms-playwright/`.

### 3. Authenticate (one-time)

```bash
notebooklm login
```

A Chromium window opens for Google sign-in. After logging in, press **Enter** in the terminal. Credentials are saved to `~/.notebooklm/` and reused automatically by every future `mosaic notebook` call.

::: tip
After the first sign-in, Playwright and Chromium are never invoked again. You can also copy `~/.notebooklm/` to another machine to skip re-authentication.
:::

### 3. Authenticate (one-time)

```bash
notebooklm login
```

This opens a Chromium browser window for Google sign-in. Credentials are stored in `~/.config/notebooklm/` and reused automatically on every subsequent `mosaic notebook` call.

If you are ever signed out, re-run `notebooklm login`.

## Usage

### From a search query

Search, download, and import in one command:

```bash
# Search all sources, download OA PDFs, create notebook
mosaic notebook create "Attention Mechanisms" \
    --query "attention is all you need" \
    --oa-only --max 10

# Also queue an Audio Overview (podcast)
mosaic notebook create "Transformers Survey" \
    --query "transformer architecture survey 2023" \
    --oa-only --podcast
```

### From a local directory

If you already have PDFs downloaded, import them directly:

```bash
mosaic notebook create "My Reading List" --from-dir ~/mosaic-papers/
```

### Full option reference

| Option | Default | Description |
|--------|---------|-------------|
| `NAME` | *(required)* | Notebook name |
| `--query`, `-q` | — | Search query (alternative to `--from-dir`) |
| `--from-dir` | — | Directory of PDFs to import (alternative to `--query`) |
| `--max`, `-n` | `10` | Max results per source when using `--query` |
| `--oa-only` | off | Only include open-access papers |
| `--podcast` | off | Queue an Audio Overview after import |

## What happens under the hood

```mermaid
flowchart LR
    Q([mosaic notebook create]) --> S[Search all sources]
    S --> D[Download OA PDFs]
    D -->|local PDF| NLM[NotebookLM notebook]
    D -->|no PDF, has URL| NLM
    NLM -->|--podcast| AO[Audio Overview]
```

1. MOSAIC searches all enabled sources with the given query.
2. For each result, it attempts to download the PDF (with Unpaywall fallback).
3. Papers with a local PDF are uploaded as files; the rest are added by URL.
4. Up to 50 sources are imported (NotebookLM's hard limit).
5. If `--podcast` is set, an Audio Overview is queued — it appears in NotebookLM Studio in a few minutes.

## Typical workflow

```bash
# 1. Find and collect papers on a topic
mosaic notebook create "Protein Folding 2024" \
    --query "protein structure prediction alphafold" \
    --oa-only --max 15 --podcast

# 2. Open the link printed by MOSAIC in your browser
# 3. Chat with the notebook, generate quizzes, flashcards, study guides…
```

## Notes

- **Source limit**: NotebookLM accepts at most 50 sources per notebook. For larger result sets, only the first 50 are imported.
- **Podcast timing**: Audio Overview generation takes 5–15 minutes. The notebook is usable immediately while the podcast renders in the background.
- **Credentials**: `notebooklm login` stores a session cookie locally. Re-run if you are signed out.
