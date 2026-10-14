# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate the virtual environment first (system Python is externally managed)
source .venv/bin/activate

make dev          # create .venv, install mosaic editable with the dev extra
make test         # pytest with coverage (writes docs/public/coverage*.json: do not commit those by accident)
make lint         # ruff check + ruff format --check (read-only)
make fmt          # ruff check --fix + ruff format

.venv/bin/pytest tests/test_search.py              # one file
.venv/bin/pytest tests/test_search.py::test_name   # one test

# Changelog (git-cliff, Conventional Commits)
git cliff --unreleased
git cliff -o CHANGELOG.md
{ printf -- "---\ntitle: Changelog\n---\n\n"; awk '/^## \[/{found=1} found' CHANGELOG.md; } > docs/guide/changelog.md

# Docs
python docs/scripts/gen_cli_reference.py            # regenerate docs/reference/* option tables from the CLI
python docs/scripts/check_doc_commands.py           # every `mosaic ...` written in the docs must parse
cd docs && npm run docs:dev                         # live site; npm run docs:build for the static one

# Run the CLI
mosaic search "transformer attention" --max 5 --source arxiv
mosaic get 10.1234/example.doi
mosaic config --show
```

Release: `./release.sh --patch | --minor | --major | X.Y.Z` (trunk: `main`). A new user-facing flag or command is
a minor bump, a fix a patch bump. PyPI publishing happens in CI on the tag push.

## Architecture

**MOSAIC** is a CLI (`mosaic` -> `mosaic/cli.py`, Typer) that searches up to 22 scientific sources in parallel,
merges duplicates, caches every result in SQLite, downloads PDFs, and runs LLM features over the library.
`docs/guide/architecture.md` has the full module map; keep it current when adding modules.

### Data flow of a search

1. `cli.py` loads config (`config.load()`: user TOML deep-merged over `_DEFAULTS`) and builds the enabled sources
   with `source_registry.build_sources()`. A source without its key reports `available() == False`.
2. `search.search_all()` queries the available sources in a thread pool (up to 8 workers; `parallel=True` by
   default), merges by `Paper.uid` (DOI > arXiv ID > PII > title slug, via `services.merge_papers`), then applies
   `SearchFilters.match` as a safety net. Source failures go to an `errors` list (shown with `--verbose`, or in
   `--json`); they never abort the search.
3. The CLI saves papers to `db.Cache` (upsert keeps the first PDF link, the longer abstract, any citation count),
   logs the search, filters and sorts (`services.filter_papers`, `sort_by_relevance`), prints the table or JSON,
   and runs downloads and exports.

### Modules by area

- **Core:** `models.py` (`Paper`, `SearchFilters`, `fold()` for accent-insensitive author matching,
  `Paper.safe_filename`), `config.py`, `source_registry.py` (`SRC_MAP` shorthands, `SHORTHAND_TO_CFG_KEY`,
  `_SOURCE_REGISTRY`), `search.py`, `services.py`, `workflows.py`, `db.py`, `parsing.py`, `errors.py`
  (`MosaicError` -> `SourceError`, `DownloadError`, `DependencyError`, `ConfigError`).
- **Sources** (`sources/`): one class per database extending `BaseSource` (`search()`, `available()`).
  `sources/base.py` also has `http_client()` with `RetryTransport` (retries 429/503 when the server asks for a
  short wait), `describe_http_error()` and `build_field_query()`. Sources: arxiv, semantic_scholar,
  sciencedirect (+ `sciencedirect_browser`), springer_browser (`sp`), springer_api (`springer`), doaj, europepmc,
  cochrane (Europe PMC, ISSN 1469-493X), openalex, base_search, core, nasa_ads, ieee, zenodo, crossref, dblp, hal,
  pubmed, pmc, biorxiv (`rxiv`), pedro (needs `acknowledge_fair_use`), scopus (`scopus_api` / `scopus_browser`),
  plus `custom.py` (JSON APIs declared in config). `unpaywall.py` is a downloader helper, not a source.
- **Getting PDFs:** `downloader.py` (cache -> known `pdf_url` -> every Unpaywall OA location + HAL `/document`
  -> saved browser session; `.part` + atomic rename; `resolve_landing` maps Elsevier linkinghub to
  ScienceDirect), `pdf.py` (`%PDF-` magic check; HTML saved as PDF is rejected), `auth.py` (Playwright sessions,
  `interactive_download`, `session_health`), `handoff.py` (`--handoff`: the user's own browser + `DownloadWatcher`
  on the Downloads folder, WSL-aware), `importer.py` (`mosaic import`: DOI from metadata, ScienceDirect
  `1-s2.0-<PII>-main` names via Crossref, or a single DOI in the text), `cite.py` (`paper_for_download`,
  citation styles), `bulk.py` (DOIs from .bib/.csv).
- **Library and LLM:** `llm.py` (the single chat-completion entry point: OpenAI, Anthropic, any
  OpenAI-compatible `base_url`; `openai_url()` accepts base URLs with or without `/v1`; `llm.timeout` config;
  `loads_json()` tolerates fenced or `<think>`-wrapped JSON from local models), `embeddings.py`
  (`EmbeddingError`), `rag.py` (chunked index in `vec_chunks`, `semantic_search`, `ask`), `ranking.py` (BM25,
  LLM scoring), `summarise.py` (`--summarise`), `compare.py`, `citations/` (OpenAlex, Crossref, OpenCitations
  reference lists; `enrichment.py`), `network.py`, `similar.py`, `watch.py` (saved searches with per-watch
  `watch_hits`).
- **Elsewhere:** `exporter.py` (bib/ris/csv/json/md/markdown), `zotero.py`, `obsidian.py`,
  `notebooklm_bridge.py`, `ui/` (Flask web UI, `jobs.py`), `gui_launcher.py` (PyInstaller desktop app),
  `data/SKILL.md` (the Claude Code skill shipped by `mosaic skill install`).

### Adding a new source

1. Create `mosaic/sources/myname.py` with a class extending `BaseSource`; set `name`, implement `search()`
   (use `http_client()` so retries apply) and `available()` if it needs a key.
2. Export it from `mosaic/sources/__init__.py`.
3. Wire it into `source_registry.py` (factory, `_SOURCE_REGISTRY`, `SRC_MAP`, `SHORTHAND_TO_CFG_KEY`) and into
   `config._DEFAULTS["sources"]`.
4. Add it to the `--source` help in `cli.py` and to `docs/guide/sources.md`, then regenerate the reference.

### Tests

- Unit tests make no network calls: patch `httpx` (see `conftest.py`: `tmp_cache`, `paper`, `make_response()`).
  Responses built from `MagicMock` need `is_error = False` where the code checks it.
- `tests/test_docs.py` fails when `docs/reference/` is stale (run `gen_cli_reference.py`) or when a documented
  `mosaic` command names an option or command that does not exist.
- CI installs `.[dev,ui,rag]`, so the sqlite-vec tests run; they are skipped locally without the `rag` extra.

## Docs

VitePress in `docs/` (config: `docs/.vitepress/config.mts`, one reading-order sidebar). Structure, mirroring
FoBiS and foresight:

- `guide/index.md`, `guide/installation.md`: start here.
- `tutorial/01..10`: one literature search (Hall thruster PIC simulation) from the first query to the citation
  network. Pages include real captured output with `<<< @/examples/output/<chapter>/<step>.txt{console}`.
- `cookbook/*.md`: one task per recipe.
- `guide/*.md`: one topic per page (sources, downloads, authenticated access, cache, watch, rag, ...).
- `reference/*.md`: one page per command; the text above `<!-- cli:begin -->` is hand-written, the option tables
  between the markers are generated (`reference/index-command.md` is `mosaic index`).

`docs/scripts/docs_examples.py` re-runs the tutorial in a scratch HOME against the live sources (it needs the
network, an Unpaywall e-mail, two PDFs and a local LLM; see its docstring) and rewrites `docs/examples/output/`.
Run it when a chapter or the CLI output changes, review the diff, then re-check the prose that quotes numbers.
`docs/make_gifs.sh` records `docs/tapes/*.tape` with VHS into `docs/public/gifs/`, in a copy of that home.

Style: second person, present tense, no em dashes, no marketing words; never paste output that was not produced
by running the command.

## Workflow rules

- **Never run `git commit`**: GPG signing needs a TTY that Claude Code lacks. Stage files and give the commit
  message (Conventional Commits, no Co-authored-by lines); the user commits, pushes and releases.
- Do not stage the user's data file `test-doi.csv`.
