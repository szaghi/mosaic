---
title: Installation
---

# Installation

mosaic needs Python 3.11 or newer. The core install has every search source, downloads, exports, the cache,
watches, and the language-model features that need no extra package; the extras below add the rest.

## With pipx

[pipx](https://pipx.pypa.io) installs command-line tools in their own environment and puts `mosaic` on your `PATH`:

```bash
pipx install mosaic-search            # core
pipx install 'mosaic-search[all]'     # core and every extra
```

Install pipx with `apt install pipx` (Debian, Ubuntu), `brew install pipx` (macOS) or
`python -m pip install --user pipx`. [uv](https://docs.astral.sh/uv/) works the same way:
`uv tool install 'mosaic-search[all]'`.

## With pip, in a virtual environment

```bash
python -m venv ~/.venvs/mosaic
source ~/.venvs/mosaic/bin/activate        # Windows: ~\.venvs\mosaic\Scripts\activate
pip install 'mosaic-search[all]'
```

## Extras

| Extra | Installs | For |
|---|---|---|
| `rag` | sqlite-vec | `mosaic index`, `ask`, `chat`, `search --semantic` |
| `analysis` | networkx | Louvain clusters in `mosaic network --cluster` (without it: connected components) |
| `browser` | Playwright | `mosaic auth login`, `get --interactive`, the Springer browser source, ScienceDirect and Scopus searches without an API key |
| `ui` | Flask, Waitress | `mosaic ui`, the web interface |
| `notebooklm` | notebooklm-py | `mosaic notebook create` |
| `all` | all of the above | |

Add an extra later by reinstalling with it (`pipx install --force 'mosaic-search[rag]'`) or by injecting its
package (`pipx inject mosaic-search sqlite-vec`).

Two extras need one more step:

- **Playwright needs a browser binary.** After installing `browser`, `notebooklm` or `all`:

  ```bash
  ~/.local/share/pipx/venvs/mosaic-search/bin/playwright install chromium   # pipx
  playwright install chromium                                                 # pip, in the venv
  ```

- **Full-text indexing reads PDFs with PyMuPDF** (AGPL-licensed), which no extra installs:
  `pipx inject mosaic-search pymupdf`. Without it, `mosaic index` embeds titles and abstracts only.

The language-model features (`--summarise`, `--sort relevance` with a model, `compare`, `ask`) talk to a server
over HTTP and need no extra: [Ollama](https://ollama.com) on your machine, or an OpenAI or Anthropic API key.
[Local RAG](/guide/rag#setting-up-the-models) shows both setups.

## Standalone app

The [GitHub releases](https://github.com/szaghi/mosaic/releases) carry the web interface packaged with its own
Python, for people who do not use a terminal:

| Platform | Asset |
|---|---|
| Windows 10/11, x86-64 | `MOSAIC-Windows.zip` |
| macOS 12+, Apple Silicon | `MOSAIC-macOS-arm64.zip` |
| Linux x86-64, glibc 2.31+ | `MOSAIC-Linux.tar.gz` |

Unpack it and start `MOSAIC`; see [Web UI](./web-ui#standalone-desktop-app-windows-macos-linux).

## From source

```bash
git clone https://github.com/szaghi/mosaic
cd mosaic
make dev          # creates .venv and installs mosaic in editable mode with the dev tools
make test
```

[Contributing](./contributing) describes the development workflow.

## Check, complete, upgrade

```bash
mosaic --version
mosaic --install-completion     # tab completion for bash, zsh or fish
pipx upgrade mosaic-search      # or: uv tool upgrade mosaic-search, pip install -U mosaic-search
```

Next: the [tutorial](/tutorial/).
