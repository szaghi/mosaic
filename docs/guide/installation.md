---
title: Installation
---

# Installation

## Standalone App — no Python required

The fastest way to get started is to download a pre-built standalone app from the [GitHub Releases page](https://github.com/szaghi/mosaic/releases). It bundles everything (Python runtime, Flask, all dependencies) into a single archive — just unzip and run.

| Platform | Asset | Requirements |
|----------|-------|--------------|
| Windows | `MOSAIC-Windows.zip` | Windows 10/11 (x86-64) |
| macOS (Apple Silicon) | `MOSAIC-macOS-arm64.zip` | macOS 12+ |
| Linux | `MOSAIC-Linux.tar.gz` | x86-64, glibc 2.31+ |

See the [Web UI guide](./web-ui#standalone-desktop-app-windows-macos-linux) for download instructions and a video walkthrough.

---

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

## Optional features

The core install covers all 21 search sources and the full CLI. The table below lists every opt-in feature and the extra dependency it requires.

| Feature | Extra | What it enables |
|---------|-------|-----------------|
| **Everything** | `[all]` | All features below in one shot |
| **Web UI** | `[ui]` | `mosaic ui` — browser-based interface |
| **Local RAG** | `[rag]` | `mosaic index` / `mosaic ask` / `mosaic chat` — local LLM Q&A over your library |
| **Louvain clustering** | `[analysis]` | `mosaic network --cluster` — Louvain community detection via networkx |
| **Browser sessions** | `[browser]` | `mosaic auth login` — download PDFs from sites requiring login |
| **NotebookLM** | `[notebooklm]` | `mosaic notebook` — create Google NotebookLM notebooks from searches |

### Install everything at once

```bash
pipx install 'mosaic-search[all]'          # pipx
uv tool install 'mosaic-search[all]'       # uv
pip install 'mosaic-search[all]'           # pip / venv
```

::: warning Playwright browser required
`[all]` installs the Playwright library but does **not** download a browser binary. Run this once after installation:

```bash
# pipx
~/.local/share/pipx/venvs/mosaic-search/bin/playwright install chromium
# uv
~/.local/share/uv/tools/mosaic-search/bin/playwright install chromium
# pip / venv
playwright install chromium
```
:::

Each individual feature also has its own subsection below.

---

## Optional: Web UI

MOSAIC includes a browser-based graphical interface. Install the `ui` extra:

```bash
pipx inject mosaic-search "flask>=3.0" "waitress>=3.0"   # pipx
uv tool inject mosaic-search "flask>=3.0" "waitress>=3.0" # uv
pip install 'mosaic-search[ui]'                            # pip / venv
```

Then launch with `mosaic ui`. See the [Web UI guide](./web-ui) for details.

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

## Optional: local RAG {#optional-rag}

To use `mosaic index`, `mosaic ask`, and `mosaic chat` you need [sqlite-vec](https://github.com/asg017/sqlite-vec), a lightweight SQLite vector extension.

```bash
pipx inject mosaic-search sqlite-vec          # pipx
uv tool inject mosaic-search sqlite-vec       # uv
pip install 'mosaic-search[rag]'              # pip / venv
```

You also need an embedding model and a generation model. The easiest local setup uses [Ollama](https://ollama.com):

```bash
# Pull an embedding model
ollama pull snowflake-arctic-embed2

# Pull a generation model
ollama pull llama3.2

# Configure MOSAIC
mosaic config \
  --embedding-model snowflake-arctic-embed2 \
  --embedding-base-url http://localhost:11434/v1 \
  --embedding-api-key ollama \
  --llm-provider openai \
  --llm-base-url http://localhost:11434/v1 \
  --llm-api-key ollama \
  --llm-model llama3.2
```

Cloud OpenAI works too — see the [RAG guide](./rag) for all setup options, model recommendations, and usage examples.

## Optional: Louvain clustering {#optional-analysis}

`mosaic network --cluster` uses connected-components by default (no extra dependency). For higher-quality Louvain community detection install the `analysis` extra:

```bash
pipx inject mosaic-search networkx          # pipx
uv tool inject mosaic-search networkx       # uv
pip install 'mosaic-search[analysis]'       # pip / venv
```

See the [Citation Network guide](./network) for usage and export options.

## Verify

```bash
mosaic --help
```

You should see the full list of commands: `search`, `get`, `index`, `ask`, `chat`, `config`, `cache`, `similar`, `notebook`, and more.

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
