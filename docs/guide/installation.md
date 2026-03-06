---
title: Installation
---

# Installation

## Requirements

- Python 3.11 or newer
- `pip`

## From PyPI (recommended)

[pipx](https://pipx.pypa.io) installs CLI tools in isolated environments and exposes them globally — no virtualenv management needed:

```bash
pipx install mosaic-search
```

If you prefer plain pip (into your current environment or virtualenv):

```bash
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

## Verify

```bash
mosaic --help
```

You should see the three available commands: `search`, `get`, and `config`.

## Shell completion

```bash
mosaic --install-completion   # bash / zsh / fish
```

## Upgrading

```bash
pipx upgrade mosaic-search      # if installed with pipx
pip install --upgrade mosaic-search   # if installed with pip
```
