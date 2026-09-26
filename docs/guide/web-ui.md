---
title: Web UI
---

# Web UI

MOSAIC includes an optional graphical web interface built with Flask, HTMX, and Pico CSS. It mirrors all the features of the CLI in a browser-based interface.

<video src="/mosaic-1.3.5-web_ui.mp4" controls style="width:100%;border-radius:8px;margin:1rem 0"></video>

## Installation

The web UI requires the `ui` extra:

```bash
pipx inject mosaic-search "flask>=3.0" "waitress>=3.0"   # pipx
uv tool inject mosaic-search "flask>=3.0" "waitress>=3.0" # uv
pip install 'mosaic-search[ui]'                            # pip / venv
```

## Launch

```bash
mosaic ui
```

This starts a local Waitress server (production-grade, multi-threaded) and opens your browser to `http://127.0.0.1:5555`.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `5555` | Port number |
| `--host` | `127.0.0.1` | Bind address (`0.0.0.0` for LAN access — see [Security](#security)) |
| `--no-browser` | off | Don't auto-open the browser |
| `--debug` | off | Use Flask dev server with hot-reload |
| `--token` | random off-loopback | Access token (env `MOSAIC_UI_TOKEN`) |
| `--no-auth` | off | Disable the access token on a network-reachable address |

```bash
mosaic ui --port 8080                 # custom port
mosaic ui --host 0.0.0.0             # accessible on LAN (token-protected)
mosaic ui --no-browser                # headless / remote
mosaic ui --debug                     # development mode (hot-reload)
```

## Pages

Every CLI workflow has a web counterpart; both call the same shared code
(`services.py` / `workflows.py`), so results, filters and side effects match.

| Page | CLI equivalent |
|------|----------------|
| Search | `mosaic search` (incl. `--cached`, `--semantic`, `--downloaded-only`, `--prefer-cache`) |
| Paper detail | `mosaic cache show`, `mosaic cite`, `mosaic get` |
| Similar | `mosaic similar` |
| Bulk | `mosaic get --from` |
| Library | `mosaic cache stats / list / verify / clean / clear / export` |
| Analysis → Compare | `mosaic compare` |
| Analysis → Network | `mosaic network` |
| NotebookLM | `mosaic notebook create` |
| AI → Index / Ask / Chat | `mosaic index`, `mosaic ask`, `mosaic chat` |
| Sessions | `mosaic auth status / logout` (log in with `mosaic auth login`) |
| Config | `mosaic config` |

### Search

The main page. Enter a query, select sources, apply filters, and view results in a paginated table.

**Features:**

- **Search in** &mdash; online sources, the local cache (keywords), or the local vector index (semantic, needs `mosaic index`)
- **Source selection** &mdash; check/uncheck individual sources (custom sources included), select all / deselect all
- **Filters** &mdash; year (range, list, or single), author, journal, field scope, raw query
- **Sort** &mdash; by default order, citations, year, or relevance (BM25/LLM; the score column is shown)
- **Post-filters** &mdash; open-access only, PDF available only, downloaded PDFs only (local modes), prefer cached records
- **Per-source progress** &mdash; live badges show which sources are done, pending, or errored
- **Parallel queries** &mdash; sources are queried concurrently (up to 8 threads) for faster results
- **Pagination** &mdash; results are paginated (25 per page) when there are many hits
- **Export** &mdash; download results as CSV, JSON, BibTeX, RIS, or Markdown (short or with abstracts)
- **Bulk actions** &mdash; download all PDFs, send to Zotero (optional collection, local API; downloaded PDFs are attached), export to Obsidian (optional subfolder)

Searches are saved to the cache and logged in History, and new papers are indexed when `rag.auto_index` is on (failures are shown, not hidden).

### Paper Detail

Click any paper title in the results table to see the full record:

- Title, authors, year, journal, volume/issue/pages
- DOI and arXiv links (clickable)
- Open Access and citation count
- Full abstract
- **Action buttons**: Open PDF, Open URL, DOI Link, Download PDF, Find Similar, Send to Zotero, Export to Obsidian
- **Cite** &mdash; BibTeX (from local metadata) or APA / MLA / Chicago / Harvard / Vancouver (via doi.org), with a copy button

### Similar Papers

Find papers related to a known DOI or arXiv ID. Uses OpenAlex `related_works` and Semantic Scholar recommendations.

### Bulk

Upload a `.bib` or `.csv` file of DOIs to download them all. Metadata already in the cache is reused for file names; results can optionally be sent to Zotero (with PDFs attached) or Obsidian.

### Library

Browse the local cache with statistics, a title/abstract filter and pagination; verify that downloaded files still exist, clean stale download records, wipe the cache, or export the (filtered) library in any supported format.

### Analysis

- **Compare** &mdash; comparison table over cached papers (filter by keyword or `.bib`/`.csv`, custom dimensions, pre-sort), exportable to Markdown, CSV or JSON.
- **Network** &mdash; most-connected papers and topic clusters of the local citation graph, exportable to JSON, Graphviz or Mermaid.

### AI (RAG)

- **Index** &mdash; build or update the vector index (optionally for a subset or a `.bib`/`.csv` file, with citation enrichment). Problems with the index (old format, model change, missing `pymupdf`/`sqlite-vec`) are shown on the page.
- **Ask** &mdash; one-shot questions with mode, top-k and subset filters (keyword, year, file); the answer can be saved as Markdown or JSON.
- **Chat** &mdash; multi-turn conversation: the last turns are sent to the LLM as context, each answer lists its source papers, and the retrieval pool can be narrowed to matching papers.

Answers are rendered as Markdown with raw HTML, script links and remote images stripped.

### NotebookLM

Create a notebook from a search or a local PDF folder. The page checks that `notebooklm-py` is installed and authenticated before starting, and the result reports how many sources were added and which artifacts were queued, failed, or skipped (e.g. when no source could be added).

### History

All past searches (from the web UI and the CLI) are saved to the local SQLite cache. The history page lists them with result counts, timestamps, and a **Re-run** button to repeat any previous search.

### Configuration

View and edit all MOSAIC settings from the browser:

- Download directory and filename pattern
- API keys for all sources (Elsevier, Semantic Scholar, CORE, NASA ADS, IEEE, Springer, NCBI, Scopus, Zenodo, Zotero)
- Unpaywall email
- Enable/disable individual sources, PEDro and Obsidian settings
- LLM and embedding settings (provider, model, key, base URL, top-k, chunk size/overlap, full-text indexing, citation boosting, auto-index)

Saved secrets are never sent back to the browser: leave a field blank to keep the stored value or tick *remove saved value* to delete it. Setting a Zotero key discovers the Zotero user ID automatically. Changes are saved to `~/.config/mosaic/config.toml`, the same file used by the CLI.

## Security

On `127.0.0.1` (the default) the web UI has no login, like any local desktop tool. In every mode:

- Requests whose `Host` header is not a loopback name (or the address passed to `--host`) are rejected, which blocks DNS-rebinding attacks.
- State-changing requests coming from another site (`Origin` / `Sec-Fetch-Site`) are rejected, so a web page cannot silently change your configuration.
- Saved API keys are never sent back to the browser.

When `--host` is not a loopback address (e.g. `0.0.0.0` for LAN access), the UI requires an **access token**. `mosaic ui` generates a random one and prints the URL to open (`http://HOST:PORT/?token=…`); the browser keeps a session cookie afterwards and the token is removed from the address bar. Scripts can send `Authorization: Bearer <token>` instead. Use `--token` (or `MOSAIC_UI_TOKEN`) to choose the token, or `--no-auth` to disable it — only on a network you fully trust, since anyone who can reach the port can read your library and change your configuration.

The Host check is disabled for wildcard bind addresses such as `0.0.0.0`. Traffic is plain HTTP; use an SSH tunnel or a reverse proxy with TLS if you need to reach the UI across untrusted networks.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| <kbd>Ctrl</kbd>+<kbd>Enter</kbd> (or <kbd>Cmd</kbd>+<kbd>Enter</kbd>) | Submit the current form |
| <kbd>/</kbd> | Focus the search input |

## Theme

Click the **&#9681;** icon in the navigation bar to cycle between auto, light, and dark mode. The setting is persisted in your browser's local storage.

## Standalone Desktop App (Windows / macOS / Linux)

Pre-built standalone executables are attached to each [GitHub release](https://github.com/szaghi/mosaic/releases) — **no Python installation required**. This is the easiest way to get started on any platform.

| Platform | Asset | Requirements |
|----------|-------|--------------|
| Windows | `MOSAIC-Windows.zip` | Windows 10/11 (x86-64) |
| macOS (Apple Silicon) | `MOSAIC-macOS-arm64.zip` | macOS 12+ (Apple Silicon) |
| Linux | `MOSAIC-Linux.tar.gz` | x86-64, glibc 2.31+ (Ubuntu 20.04+, Debian 11+) |

The app bundles its own Python runtime and Flask server. It starts a local server on port 5555 and opens your **default browser** automatically. No installation step, no extra runtimes needed.

### How to download from GitHub

1. Open the [Releases page](https://github.com/szaghi/mosaic/releases) and click the latest release.
2. Scroll down to **Assets** at the bottom of the release notes.
3. Click the archive for your platform (`MOSAIC-Windows.zip`, `MOSAIC-macOS-arm64.zip`, or `MOSAIC-Linux.tar.gz`) to download it.

The video below shows the full download-and-run flow on Windows:

<video src="/mosaic-release-win-download.mp4" controls style="width:100%;border-radius:8px;margin:1rem 0"></video>

### Extract and run

```bash
# Windows (PowerShell)
Expand-Archive MOSAIC-Windows.zip .
.\MOSAIC\MOSAIC.exe

# macOS
unzip MOSAIC-macOS-arm64.zip
open MOSAIC.app   # or double-click in Finder

# Linux
tar xzf MOSAIC-Linux.tar.gz
./MOSAIC/MOSAIC
```

> **Windows SmartScreen / macOS Gatekeeper** — because the app is not yet code-signed, your OS may warn you the first time. On Windows click **More info → Run anyway**; on macOS right-click the app and choose **Open**.

## Architecture Notes

- **Server**: [Waitress](https://docs.pylonsproject.org/projects/waitress/) (pure-Python, multi-threaded WSGI server). `--debug` mode falls back to Flask's built-in dev server for hot-reload.
- **Frontend**: [HTMX](https://htmx.org/) for dynamic interactions (no page reloads), [Pico CSS](https://picocss.com/) for styling (~130 KB total static assets).
- **Background jobs**: Long-running searches and PDF downloads run in a thread pool and report progress via polling. An SSE stream endpoint (`/stream/<job_id>`) is also available.
- **Database**: Shares the same SQLite cache as the CLI (`~/.local/share/mosaic/cache.db`). Papers found via the UI are available to the CLI and vice versa.
