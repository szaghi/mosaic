---
title: Maintenance
---

# Maintenance

Recipes for the files mosaic keeps: where they are, how to back them up, check them, and start over.

[[toc]]

## Where mosaic keeps its files

| What | Where | Change with |
|---|---|---|
| configuration and API keys | `~/.config/mosaic/config.toml` | `mosaic config`, or edit the file |
| browser sessions | `~/.config/mosaic/sessions/NAME.json` and `NAME.meta.json` | `mosaic auth login`, `mosaic auth logout` |
| cache: papers, downloads, searches, watches, vector index, citation graph | `~/.local/share/mosaic/cache.db` | `mosaic config --db-path` |
| the PDFs | `~/mosaic-papers/` | `mosaic config --download-dir` |

```bash
mosaic config --show
```

prints the whole configuration as JSON, API keys included: do not paste it in a public issue. Guide: [Configuration](/guide/configuration).

## What the cache holds

```bash
mosaic cache stats
mosaic cache list -n 20 -q "hall thruster"
mosaic cache show 10.1063/1.4972269
```

`stats` counts the papers (with an abstract, open access, with a PDF link), the recorded downloads, the logged
searches and the size of the database. Guide: [The cache](/guide/cache).

## Export or back up the cache

```bash
mosaic cache export library.bib
mosaic cache export hall.csv --query "hall thruster" --limit 200
cp ~/.local/share/mosaic/cache.db ~/backup/mosaic-cache-$(date +%F).db
```

`cache export` writes the cached papers in any `--output` format (`.bib`, `.ris`, `.csv`, `.json`, `.md`,
`.markdown`), all of them or those matching `--query`. Copying `cache.db` while mosaic is not running keeps
everything, watches and vector index included.

## A library moved or cleaned by hand

```bash
mosaic cache verify
mosaic cache clean
```

`verify` checks every recorded download: the file exists and starts with the PDF signature. `clean` forgets the
records of missing files and of files that are not PDFs, so the next `mosaic get` downloads them again; it deletes
no file. After moving the library, point mosaic at it with `mosaic config --download-dir` and run both.

## Start over

```bash
mosaic cache clear --yes
```

Deletes every cached paper, download record, logged search, the vector index and the citation graph. Your
watches, configuration, sessions and PDFs stay. Without `--yes` it asks first.

## Upgrade mosaic

```bash
pipx upgrade mosaic-search          # installed with pipx
uv tool upgrade mosaic-search       # installed with uv
pip install --upgrade mosaic-search # inside a virtual environment
```

Extras installed before (`[all]`, `[rag]`, ...) are kept by `pipx upgrade` and `uv tool upgrade`. The cache and the
configuration carry over between versions. Guide: [Installation](/guide/installation).

## Shell completion

```bash
mosaic --install-completion
```

Installs completion of commands, options and source shorthands for bash, zsh or fish (the shell you run it from);
open a new shell to use it.

## Check the version

```bash
mosaic --version
```

Quote it when you report a problem, with the output of the failing command run with `mosaic --verbose`.
