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
| `--host` | `127.0.0.1` | Bind address (`0.0.0.0` for LAN access) |
| `--no-browser` | off | Don't auto-open the browser |
| `--debug` | off | Use Flask dev server with hot-reload |

```bash
mosaic ui --port 8080                 # custom port
mosaic ui --host 0.0.0.0             # accessible on LAN
mosaic ui --no-browser                # headless / remote
mosaic ui --debug                     # development mode (hot-reload)
```

## Pages

### Search

The main page. Enter a query, select sources, apply filters, and view results in a paginated table.

**Features:**

- **Source selection** &mdash; check/uncheck individual sources, select all / deselect all
- **Filters** &mdash; year (range, list, or single), author, journal, field scope
- **Sort** &mdash; by default order, citations, or year
- **Post-filters** &mdash; open-access only, PDF available only
- **Per-source progress** &mdash; live badges show which sources are done, pending, or errored
- **Parallel queries** &mdash; sources are queried concurrently (up to 8 threads) for faster results
- **Pagination** &mdash; results are paginated (25 per page) when there are many hits
- **Export** &mdash; download results as CSV, JSON, BibTeX, or Markdown

### Paper Detail

Click any paper title in the results table to see the full record:

- Title, authors, year, journal, volume/issue/pages
- DOI and arXiv links (clickable)
- Open Access and citation count
- Full abstract
- **Action buttons**: Open PDF, Open URL, DOI Link, Download PDF, Find Similar

### Similar Papers

Find papers related to a known DOI or arXiv ID. Uses OpenAlex `related_works` and Semantic Scholar recommendations.

### History

All past searches are saved to the local SQLite cache. The history page lists them with result counts, timestamps, and a **Re-run** button to repeat any previous search.

### Configuration

View and edit all MOSAIC settings from the browser:

- Download directory and filename pattern
- API keys for all sources (Elsevier, Semantic Scholar, CORE, NASA ADS, IEEE, Springer, NCBI, Zotero)
- Unpaywall email
- Enable/disable individual sources

Changes are saved to `~/.config/mosaic/config.toml`, the same file used by the CLI.

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
