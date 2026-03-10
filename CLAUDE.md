# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate the virtual environment first (system Python is externally managed)
source .venv/bin/activate

# Preview what the next changelog would look like (unreleased commits)
git cliff --unreleased

# Regenerate CHANGELOG.md and docs/guide/changelog.md manually
git cliff -o CHANGELOG.md
{ printf -- "---\ntitle: Changelog\n---\n\n"; awk '/^## \[/{found=1} found' CHANGELOG.md; } > docs/guide/changelog.md

# Install for development
pip install -e ".[dev]"

# Run all tests with coverage
pytest

# Run a single test file
pytest tests/test_search.py

# Run a single test
pytest tests/test_search.py::test_name

# Run the CLI
python -m mosaic search "transformer attention"
mosaic search "transformer attention" --max 5 --source arxiv
mosaic get 10.1234/example.doi
mosaic config --show
```

## Architecture

**MOSAIC** is a CLI tool (`mosaic` entry point → `mosaic/cli.py`) that fans out paper searches across multiple scientific sources, deduplicates results, caches them locally, and can download PDFs.

### Data flow

1. `cli.py` loads config, instantiates enabled sources via `_build_sources()`, calls `search_all()`.
2. `search.py:search_all()` iterates sources sequentially, merges duplicates by `Paper.uid` (preferring richer data), applies `SearchFilters` as a post-processing safety net.
3. Results are saved to a SQLite cache (`db.py:Cache`) and optionally downloaded via `downloader.py`.

### Key modules

- **`models.py`** — `Paper` dataclass (central data model) and `SearchFilters` (year/author/journal filtering). `Paper.uid` is the deduplication key: prefers DOI > arxiv_id > pii > title slug.
- **`sources/base.py`** — `BaseSource` ABC with `search()` and `available()`. All sources in `sources/` implement this interface.
- **`sources/`** — Twenty sources: `arxiv`, `semantic_scholar`, `sciencedirect` (API key or browser session), `sciencedirect_browser`, `springer_browser` (Playwright, shorthand `sp`), `springer_api` (free API key, shorthand `springer`), `doaj`, `europepmc`, `openalex`, `base_search`, `core` (free API key), `nasa_ads` (free API token), `ieee` (free API key, shorthand `ieee`), `zenodo` (no auth required), `crossref` (no auth required), `dblp` (no auth required), `hal` (no auth required), `pubmed` (no auth required, API key optional), `pmc` (PubMed Central, always OA + direct PDF, API key optional; same NCBI key as pubmed), `biorxiv` (bioRxiv + medRxiv, shorthand `rxiv`; searches both servers via website search, fetches metadata from `api.biorxiv.org`; always OA). `unpaywall.py` is a helper (not a search source) used by the downloader.
- **`similar.py`** — `find_similar(identifier, max_results, *, oa_email, ss_api_key)` fans out to OpenAlex `related_works` (always) and Semantic Scholar recommendations (when API key configured), deduplicates by `Paper.uid`, and returns `(seed_title, papers)`. Used by `mosaic similar` CLI command.
- **`bulk.py`** — `read_dois(path)` extracts DOIs from `.bib` (regex) or `.csv` (DictReader) files. Used by `mosaic get --from`.
- **`zotero.py`** — `ZoteroClient` class supporting both local API (`http://localhost:23119`) and web API (`https://api.zotero.org`). Auto-detects mode from config (`zotero.api_key`). Key methods: `is_reachable()`, `discover_user_id()`, `ensure_collection(name)`, `add_papers(papers)`, `attach_pdf(item_key, path)`. PDF attachment is local-only (linked_file); web mode is metadata-only in v1.
- **`db.py`** — SQLite with two tables: `papers` (upsert on uid, updates pdf_url/abstract/is_open_access) and `downloads` (tracks local file paths and status).
- **`config.py`** — Reads/writes `~/.config/mosaic/config.toml`; deep-merges user config over defaults. DB lives at `~/.local/share/mosaic/cache.db`, downloads at `~/mosaic-papers/`. Zotero config under `[zotero]` section (`api_key`, `user_id`).

### Adding a new source

1. Create `mosaic/sources/myname.py` with a class extending `BaseSource`.
2. Set `name` class attribute and implement `search()` returning `list[Paper]`.
3. Export from `mosaic/sources/__init__.py`.
4. Wire into `cli.py:_build_sources()`.

### Tests

Tests use `unittest.mock` to patch `httpx` calls — no real network requests. `conftest.py` provides `tmp_cache` (in-memory SQLite) and `paper` fixtures, and a `make_response()` helper for building mock httpx responses. Coverage JSON is written to `docs/public/` after each test run.

### Docs

VitePress site in `docs/`. Build with `npm run docs:build` from the `docs/` directory.

## Workflow rules

- **Never run `git commit`** — generate commit messages with `/semantic-commit`
  and let the user paste them in their own terminal (GPG signing requires a TTY
  that Claude Code does not have).
