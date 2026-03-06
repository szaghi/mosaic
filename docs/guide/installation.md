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

**Step 1 — install notebooklm-py with browser support** (required for the one-time Google sign-in):

```bash
pip install "notebooklm-py[browser]"
playwright install chromium
```

**Step 2 — inject it into your MOSAIC installation:**

```bash
pipx inject mosaic-search notebooklm-py   # pipx
uv tool inject mosaic-search notebooklm-py   # uv
pip install 'mosaic-search[notebooklm]'      # pip / venv
```

**Step 3 — authenticate once:**

```bash
notebooklm login
```

A Chromium window opens for Google sign-in. After that, `mosaic notebook create` works without a browser.

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
