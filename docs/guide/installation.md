---
title: Installation
---

# Installation

## Requirements

- Python 3.11 or newer

## From PyPI

### pipx (recommended)

[pipx](https://pipx.pypa.io) is the standard way to install Python CLI tools. It creates an isolated environment automatically and puts `mosaic` on your `PATH` — no manual virtualenv needed:

```bash
pipx install mosaic-search
```

Install pipx itself with `apt install pipx` (Debian/Ubuntu), `brew install pipx` (macOS), or `pip install pipx`.

### uv (fastest)

[uv](https://docs.astral.sh/uv/) is a modern, significantly faster alternative to pipx for installing tools:

```bash
uv tool install mosaic-search
```

### pip (inside a virtualenv)

Modern Linux and macOS systems protect the system Python from `pip` (PEP 668). Always install into a virtual environment:

```bash
python -m venv ~/.venvs/mosaic
source ~/.venvs/mosaic/bin/activate   # Windows: .venvs\mosaic\Scripts\activate
pip install mosaic-search
```

## From source

```bash
git clone https://github.com/szaghi/mosaic
cd mosaic
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## Optional: NotebookLM integration

To use `mosaic notebook create` you need [notebooklm-py](https://github.com/teng-lin/notebooklm-py), an unofficial Python client for Google NotebookLM.

**Step 1 — inject notebooklm-py into MOSAIC** (`--include-apps` exposes the `notebooklm` CLI; `[browser]` pulls in Playwright for the one-time sign-in):

```bash
pipx inject --include-apps mosaic-search "notebooklm-py[browser]"   # pipx
uv tool inject --include-apps mosaic-search "notebooklm-py[browser]"   # uv
pip install 'mosaic-search[notebooklm]'                                  # pip / venv
```

**Step 2 — install the Chromium browser** (pipx/uv bury `playwright` inside the tool venv so call it with its full path):

```bash
~/.local/share/pipx/venvs/mosaic-search/bin/playwright install chromium   # pipx
~/.local/share/uv/tools/mosaic-search/bin/playwright install chromium      # uv
playwright install chromium                                                  # pip / venv
```

**Step 3 — authenticate once:**

```bash
notebooklm login
```

A browser window opens for Google sign-in. After that, `mosaic notebook create` works without a browser.

## Optional: browser sessions {#optional-browser-sessions}

To use `mosaic auth login` for downloading PDFs from sites that require a
login (institutional repositories, publisher portals, etc.) you need
Playwright installed.

**Step 1 — install the extra:**

```bash
pipx inject mosaic-search "playwright>=1.40"   # pipx
uv tool inject mosaic-search "playwright>=1.40"   # uv
pip install 'mosaic-search[browser]'               # pip / venv
```

**Step 2 — install at least one browser** (Chromium is recommended):

```bash
# pipx / uv — call playwright inside the tool venv
~/.local/share/pipx/venvs/mosaic-search/bin/playwright install chromium
~/.local/share/uv/tools/mosaic-search/bin/playwright install chromium

# pip / venv
playwright install chromium
```

Firefox and WebKit are also supported — MOSAIC auto-detects which browser
is available and uses the first one found (Chromium → Firefox → WebKit).

**Step 3 — log in to a site once:**

```bash
mosaic auth login elsevier --url https://www.sciencedirect.com/user/login
```

See [Authenticated Access](./authenticated-access) for the full guide.

## Verify

```bash
mosaic --help
```

You should see the available commands: `search`, `get`, `config`, and `notebook`.

## Shell completion

```bash
mosaic --install-completion   # bash / zsh / fish
```

## Upgrading

```bash
pipx upgrade mosaic-search        # if installed with pipx
uv tool upgrade mosaic-search     # if installed with uv
pip install --upgrade mosaic-search   # if installed with pip in a venv
```
