---
title: Web UI
---

# Web UI

`mosaic ui` serves a browser interface to the same configuration and cache as the command line: search with
filters and per-source progress, find similar papers, bulk-download a `.bib` or `.csv`, ask your library, export to
Zotero and Obsidian, and edit the settings. A paper you find in one appears in the other.

<video src="/mosaic-1.3.5-web_ui.mp4" controls style="width:100%;border-radius:8px;margin:1rem 0"></video>

<small>Recorded with version 1.3.5; later versions add the Sessions and AI pages.</small>

## Launch

The UI needs the `ui` extra (Flask and Waitress), included in `[all]`:

```bash
pipx install 'mosaic-search[ui]'      # or: pip install 'mosaic-search[ui]'
mosaic ui
```

mosaic starts a Waitress server on `http://127.0.0.1:5555` and opens it in your browser after a second.

```bash
mosaic ui --port 8080          # another port
mosaic ui --host 0.0.0.0       # reachable from other machines on your network
mosaic ui --no-browser         # do not open a browser (a remote machine, a container)
mosaic ui --debug              # Flask's development server, reloading on code changes
```

::: warning
The UI has no login. With `--host 0.0.0.0`, anyone who reaches the port can run searches, download files and read
and change your configuration, API keys included.
:::

## Pages

| Page | What it does |
|---|---|
| Search | The query, sources (checkboxes), results per source, sort (citations, year, relevance), open-access and PDF switches, cache only and prefer cache, year, author, journal, field and raw query. Badges show each source's progress; sources are queried in parallel, at most 8 at a time. Results come 25 per page. From the results: export as CSV, JSON, BibTeX or Markdown, send to Zotero (optionally into a collection) or Obsidian. |
| Paper | Click a title: every field, the abstract, and buttons to open the PDF, the page or the DOI, download the PDF, find similar papers, and add the paper to Zotero. |
| Similar | Papers related to a DOI or arXiv ID, as [`mosaic similar`](/guide/similar). |
| Bulk | Upload a `.bib` or `.csv` and download every DOI in it, as `mosaic get --from`. |
| NotebookLM | Create a notebook from a search, as [`mosaic notebook create`](/guide/notebooklm). |
| History | Past searches, from the UI and from `mosaic search`, with their result counts and a button to run one again. |
| Sessions | Saved browser sessions, when each was saved and whether it still looks valid; delete one here. Create sessions with `mosaic auth login` ([authenticated access](/guide/authenticated-access)). |
| AI | Build the index, ask a question in one of the four modes, or chat, as [`mosaic index`, `ask`, `chat`](/guide/rag). Chat history lives in the server's memory and is lost when it stops. |
| Config | Download folder, file name pattern, rate limit, cache path, API keys, Unpaywall e-mail, enabled sources, PEDro, Obsidian, LLM and RAG settings. Saving writes `~/.config/mosaic/config.toml`. |

Keys: <kbd>/</kbd> moves to the search box, <kbd>Ctrl</kbd>+<kbd>Enter</kbd> (<kbd>Cmd</kbd>+<kbd>Enter</kbd> on
macOS) submits the form. The &#9681; icon in the navigation bar cycles the automatic, light and dark themes.

## Standalone desktop app (Windows, macOS, Linux) {#standalone-desktop-app-windows-macos-linux}

Each [GitHub release](https://github.com/szaghi/mosaic/releases) carries the web UI as a self-contained app, built
with PyInstaller: no Python to install.

| Platform | Asset | Requirements |
|---|---|---|
| Windows | `MOSAIC-Windows.zip` | Windows 10 or 11, x86-64 |
| macOS | `MOSAIC-macOS-arm64.zip` | macOS 12 or later, Apple Silicon |
| Linux | `MOSAIC-Linux.tar.gz` | x86-64, glibc 2.31 or later (Ubuntu 20.04, Debian 11) |

Download the archive for your platform from the release's Assets, extract it, and run it:

```bash
# Windows (PowerShell)
Expand-Archive MOSAIC-Windows.zip .
.\MOSAIC\MOSAIC.exe

# macOS
unzip MOSAIC-macOS-arm64.zip
open MOSAIC.app

# Linux
tar xzf MOSAIC-Linux.tar.gz
./MOSAIC/MOSAIC
```

<video src="/mosaic-release-win-download.mp4" controls style="width:100%;border-radius:8px;margin:1rem 0"></video>

The app serves the UI on `http://127.0.0.1:5555` and opens it in a window of its own: an `--app` window of Chrome,
Edge or Chromium when one is installed (no address bar), otherwise a new Firefox window, otherwise your default
browser. The app is not code-signed: the first time, Windows SmartScreen asks you to confirm (More info, Run
anyway) and macOS Gatekeeper wants a right-click, Open.

## How it works

- Waitress serves the Flask app; `--debug` uses Flask's development server instead.
- The pages use [HTMX](https://htmx.org/) and [Pico CSS](https://picocss.com/), shipped with mosaic: no CDN.
- Searches, downloads and exports run as background jobs in a pool of 4 threads; the page polls their status
  (`/search/status/<job_id>` and the like). `/stream/<job_id>` serves the same status as server-sent events.
- The UI opens the same SQLite cache as the CLI (`db_path`).

See also: [`mosaic ui`](/reference/ui), [installation](/guide/installation).
