# Contributing to MOSAIC

Thank you for taking the time to contribute! MOSAIC is free and open-source
software and every kind of contribution is welcome — bug reports, feature
requests, documentation improvements, new source implementations, and code
fixes.

---

## Table of contents

1. [Code of Conduct](#code-of-conduct)
2. [How to report a bug](#how-to-report-a-bug)
3. [How to request a feature](#how-to-request-a-feature)
4. [Development setup](#development-setup)
5. [Project structure](#project-structure)
6. [Coding style](#coding-style)
7. [Tests](#tests)
8. [Commit messages](#commit-messages)
9. [Pull requests](#pull-requests)
10. [Adding a new built-in source](#adding-a-new-built-in-source)
11. [Documentation](#documentation)
12. [CI pipeline](#ci-pipeline)
13. [Release process](#release-process)

---

## Code of Conduct

This project follows the
[Contributor Covenant Code of Conduct v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
In short: be kind, be respectful, and assume good faith. Harassment of any
kind will not be tolerated.

Violations can be reported to the maintainer at **stefano.zaghi@gmail.com**.
All reports will be kept confidential.

---

## How to report a bug

1. **Search first** — check [open issues](https://github.com/szaghi/mosaic/issues)
   to see if the bug has already been reported.
2. If not, [open a new issue](https://github.com/szaghi/mosaic/issues/new?template=bug_report.md)
   using the **Bug report** template.
3. Include at minimum:
   - MOSAIC version (`mosaic --version`)
   - Python version (`python --version`)
   - Operating system
   - The exact command that triggered the bug
   - Full terminal output (including tracebacks)
   - Expected vs actual behaviour

---

## How to request a feature

1. **Search first** — check [open issues](https://github.com/szaghi/mosaic/issues)
   and [discussions](https://github.com/szaghi/mosaic/discussions).
2. [Open a new issue](https://github.com/szaghi/mosaic/issues/new?template=feature_request.md)
   using the **Feature request** template.
3. Describe the use case, not just the solution — explaining *why* you need
   something helps design the right interface.

---

## Development setup

### Prerequisites

- Python 3.11 or 3.12
- [git](https://git-scm.com/)
- [pipx](https://pipx.pypa.io/) or a virtualenv manager of your choice
- [git-cliff](https://git-cliff.org/) — only needed if you update the changelog
- [Node.js >= 20](https://nodejs.org/) — only needed if you update the docs

### Fork and clone

```bash
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/<your-username>/mosaic.git
cd mosaic

# 2. Add the upstream remote
git remote add upstream https://github.com/szaghi/mosaic.git
```

### Create a virtual environment and install

```bash
# Create and activate a venv (required — system Python is externally managed)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Core package + all dev dependencies
pip install -e ".[dev]"

# Optional extras
pip install -e ".[dev,notebooklm]"   # NotebookLM integration
pip install -e ".[dev,browser]"      # Playwright browser sources
pip install -e ".[dev,ui]"           # Flask web UI
pip install -e ".[dev,desktop]"      # Standalone desktop app (PyInstaller)
```

### Verify the setup

```bash
pytest                              # all tests should pass
mosaic --version                    # should print the current version
```

### Testing local changes when using a pipx install

If you installed MOSAIC with pipx (`pipx install mosaic-search`) and want to
keep that install as your daily driver while iterating on source changes, use
the `make dev` target instead of editing files in the pipx venv by hand:

```bash
make dev
```

This reinstalls the package from the local source tree into the pipx venv
(`~/.local/share/pipx/venvs/mosaic-search/`) with `pip install --no-deps`.
The installed `mosaic` command on your `PATH` immediately reflects every
change — no manual file copying needed.

Run it after every edit session before testing with the CLI:

```bash
# edit source files ...
make dev
mosaic search "..." --source pubmed
```

> **Adding a new core dependency to `pyproject.toml`?**
> `make dev` uses `--no-deps` and will **not** install new packages into the pipx venv.
> Run `pipx inject` once after updating `pyproject.toml`:
>
> ```bash
> pipx inject mosaic-search <new-package>
> # e.g.: pipx inject mosaic-search rank-bm25
> ```
>
> You only need to do this once per new dependency. After that, `make dev` works
> as normal. When the package is published to PyPI, users get the dependency
> automatically via the normal `pipx install` / `pip install` flow.

`pipx upgrade mosaic-search` continues to work normally and will overwrite the
local build with the latest PyPI release whenever you want to go back to a
stable version.

---

## Project structure

```
mosaic/
├── mosaic/
│   ├── cli.py              # Typer app — entry point and command wiring
│   ├── models.py           # Paper dataclass and SearchFilters
│   ├── search.py           # search_all() — fan-out and deduplication
│   ├── source_registry.py  # Source registry, factory functions, shorthand mappings
│   ├── services.py         # Shared business logic (filter building, paper merging)
│   ├── workflows.py        # Multi-step orchestration (Zotero/Obsidian export, batch download)
│   ├── parsing.py          # Shared parsing utilities (year, authors, DOI, HTML)
│   ├── errors.py           # Custom exception hierarchy and logging setup
│   ├── config.py           # load/save ~/.config/mosaic/config.toml
│   ├── db.py               # SQLite cache (papers + downloads)
│   ├── downloader.py       # PDF download — pdf_url -> Unpaywall -> browser session
│   ├── auth.py             # Browser session management (Playwright)
│   ├── exporter.py         # Export to .md / .markdown / .csv / .json / .bib
│   ├── bulk.py             # DOI extraction from .bib / .csv files
│   ├── similar.py          # find_similar() via OpenAlex + Semantic Scholar
│   ├── zotero.py           # Zotero integration (local + web API)
│   ├── obsidian.py         # Obsidian vault export
│   ├── notebooklm_bridge.py # NotebookLM notebook creation
│   ├── gui_launcher.py     # Standalone desktop app launcher (PyInstaller)
│   └── sources/
│       ├── base.py         # BaseSource ABC + shared helpers
│       ├── arxiv.py
│       ├── semantic_scholar.py
│       ├── sciencedirect.py
│       ├── sciencedirect_browser.py
│       ├── scopus_api.py
│       ├── scopus_browser.py
│       ├── springer_api.py
│       ├── springer_browser.py
│       ├── doaj.py
│       ├── europepmc.py
│       ├── openalex.py
│       ├── base_search.py
│       ├── core.py
│       ├── nasa_ads.py
│       ├── ieee.py
│       ├── zenodo.py
│       ├── crossref.py
│       ├── dblp.py
│       ├── hal.py
│       ├── pubmed.py
│       ├── pmc.py
│       ├── biorxiv.py
│       ├── pedro.py
│       ├── custom.py       # Generic TOML-driven source
│       └── unpaywall.py    # PDF resolver (not a search source)
├── tests/                  # pytest test suite (mirrors mosaic/ structure)
├── docs/                   # VitePress documentation site
│   ├── guide/              # Markdown content pages
│   └── .vitepress/         # VitePress config and theme
├── pyproject.toml          # Build config, dependencies, tool settings
├── cliff.toml              # git-cliff changelog config
└── CHANGELOG.md
```

**Data flow:**
`cli.py` loads config → `source_registry.py:build_sources()` instantiates enabled sources
→ `search.py:search_all()` iterates sources, merges duplicates by `Paper.uid`
→ `db.py:Cache.save()` persists results → display table
→ optional download / export / Zotero / NotebookLM

For the full architecture description see `CLAUDE.md`.

---

## Coding style

MOSAIC uses [Ruff](https://docs.astral.sh/ruff/) for both linting and
formatting, configured in `pyproject.toml` under `[tool.ruff]`.

### Running Ruff

```bash
# Check for lint issues
ruff check .

# Auto-fix what Ruff can
ruff check --fix .

# Format code
ruff format .
```

### Key settings

| Setting | Value |
|---------|-------|
| Target version | Python 3.11 |
| Line length | 100 |
| Quote style | double |
| Indent style | spaces |

### Enabled rule sets

The project enables a broad set of Ruff rules — see `[tool.ruff.lint]` in
`pyproject.toml` for the full list. The main categories are:

- **E/W** — pycodestyle errors and warnings
- **F** — pyflakes
- **I** — isort (import sorting)
- **N** — pep8-naming
- **UP** — pyupgrade
- **B** — flake8-bugbear
- **SIM** — flake8-simplify
- **S** — flake8-bandit (security)
- **PT** — flake8-pytest-style
- **C4** — flake8-comprehensions
- **RUF** — Ruff-specific rules

Some rules are intentionally ignored (e.g. `T201` for print statements in this
CLI tool, `S101` for asserts in tests). Per-file ignores are configured for
`tests/**` and `mosaic/cli.py`.

### General conventions

- **`from __future__ import annotations`** at the top of every module
  (enables postponed evaluation of annotations, required for `X | Y` union
  syntax on Python 3.11).
- **Type annotations** on all public function signatures.
- **Imports order:** standard library, third-party, local — separated by blank
  lines. Ruff's isort integration enforces this.
- **No docstrings needed** for private helpers whose name is self-explanatory.
  Add a docstring when the *why* is not obvious from the code.

---

## Tests

All tests live in `tests/` and use `pytest` with `unittest.mock` — **no real
network requests are made**.

### Running tests

```bash
# Run the full suite with coverage
pytest

# Run a single file
pytest tests/test_sources.py

# Run a single test
pytest tests/test_sources.py::test_name
```

Coverage is configured in `pyproject.toml` under `[tool.pytest.ini_options]`
and `[tool.coverage.*]`. The default `addopts` includes
`--cov=mosaic --cov-report=term-missing`, so every `pytest` invocation
reports coverage.

### Writing tests

- **Mock HTTP at the `httpx` level** using `unittest.mock.patch`. Patch at the
  source module level, e.g. `mosaic.sources.zenodo.httpx.get`, not `httpx.get`
  globally.
- **Use `conftest.py` fixtures:**
  - `tmp_cache` — in-memory SQLite `Cache` instance
  - `paper` — a sample `Paper` object (Attention Is All You Need)
  - `make_response(text, json_data, status_code)` — builds a mock `httpx`
    response with `.status_code`, `.text`, `.json()`, and `.raise_for_status()`
- **Name tests descriptively**: `test_<what>_<condition>` (e.g.
  `test_field_title_sends_ti_prefix`).
- Every new feature or bug fix must come with a test that validates it.

### Example

```python
from unittest.mock import patch

from conftest import make_response
from mosaic.sources.myname import MySource

def test_myname_basic_search():
    mock_data = {"results": [{"title": "Test Paper", "year": 2024}]}
    with patch(
        "mosaic.sources.myname.httpx.get",
        return_value=make_response(json_data=mock_data),
    ):
        papers = MySource().search("test query")
    assert len(papers) == 1
    assert papers[0].title == "Test Paper"
```

### Coverage

Coverage JSON and a Shields.io badge payload are written to `docs/public/`
after each test run (via the `pytest_sessionfinish` hook in `conftest.py`).
Do not manually edit those files.

---

## Commit messages

MOSAIC uses [Conventional Commits v1.0.0](https://www.conventionalcommits.org/).
The changelog is generated automatically by
[git-cliff](https://git-cliff.org/) based on commit types.

```
<type>[(<scope>)]: <description>

[optional body — wrap at 72 chars]

[optional footers]
```

| Type | When to use | Appears in changelog |
|------|-------------|----------------------|
| `feat` | New feature | **Added** |
| `fix` | Bug fix | **Fixed** |
| `perf` | Performance improvement | **Performance** |
| `refactor` | Restructure, no feature/fix | **Changed** |
| `docs` | Documentation only | **Documentation** |
| `test` | Test changes only | *(omitted)* |
| `chore` | Build, tooling, dependencies | *(omitted)* |
| `ci` | CI/CD pipeline changes | *(omitted)* |

**Rules:**
- Subject line: max 72 chars, imperative mood, lowercase, no trailing period.
- Scope: the module or area most affected (e.g. `cli`, `sources`, `exporter`).
- Breaking changes: add `!` after type/scope **and** a `BREAKING CHANGE:`
  footer.

**Examples:**

```
feat(sources): add HAL open archive as built-in source

fix(cli): prevent DOI column from being truncated in results table

docs(custom-sources): add two-source HAL/Zenodo example

test(sources): fix PubMed/PMC tests to match updated source implementation

feat(cli)!: rename --oa-only to --open-access

BREAKING CHANGE: --oa-only flag renamed to --open-access for clarity.
```

---

## Pull requests

### Before opening a PR

1. **Sync with upstream:**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```
2. **Run the full test suite** — `pytest` must pass with no failures.
3. **Run the linter** — `ruff check .` must report no errors.
4. **Update documentation** if your change affects user-visible behaviour,
   CLI flags, config keys, or the data model.

### Branch naming

Use the format `<type>/<short-description>`:

```
feat/hal-source
fix/doi-truncation
docs/custom-sources-example
refactor/search-dedup
```

### PR checklist

- [ ] Tests added or updated for the change
- [ ] All tests pass locally (`pytest`)
- [ ] `ruff check .` reports no errors
- [ ] Docs updated if behaviour changed
- [ ] Commit messages follow Conventional Commits
- [ ] PR title follows Conventional Commits format (used as the squash commit
      message)
- [ ] No unrelated changes mixed in

### Review process

- PRs are reviewed by the maintainer, typically within a few days.
- Expect at least one round of feedback.
- Keep the PR focused — one logical change per PR makes review faster.
- Prefer rebase over merge commits when incorporating review feedback.

---

## Adding a new built-in source

### 1. Create the source module

Create `mosaic/sources/<name>.py` with a class extending `BaseSource`:

```python
"""My New Source — brief description of the API."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource, build_field_query, extract_year_range


class MySource(BaseSource):
    """Search source for My Service.

    Attributes:
        name: Human-readable source name used for display and filtering.
    """

    name = "My Source"

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    def available(self) -> bool:
        return bool(self._api_key)   # or True if no auth needed

    def search(
        self,
        query: str,
        max_results: int = 25,
        filters: SearchFilters | None = None,
    ) -> list[Paper]:
        q = build_field_query(query, filters, "title:{}", "abstract:{}")
        # Call the API, parse response, return list[Paper]
        ...
        return [self._parse(item) for item in results]

    def _parse(self, item: dict) -> Paper:
        return Paper(
            title=item.get("title", ""),
            authors=item.get("authors", []),
            year=item.get("year"),
            doi=item.get("doi"),
            abstract=item.get("abstract"),
            source=self.name,
        )
```

Use `httpx` for all HTTP requests. See `mosaic/sources/zenodo.py` or
`mosaic/sources/hal.py` for complete, simple examples. Use the shared helpers
`build_field_query()` and `extract_year_range()` from `mosaic.sources.base`
to handle field scoping and year filters consistently.

### 2. Export from `mosaic/sources/__init__.py`

Add an import and include the class in `__all__`:

```python
from mosaic.sources.myname import MySource
```

### 3. Wire into `mosaic/source_registry.py`

Four changes are needed in `source_registry.py`:

1. **Import** the class at the top of the file (from `mosaic.sources`).
2. **Add a factory function** that receives `(cfg, src)` and returns an instance:
   ```python
   def _make_myname(_cfg: dict, src: dict) -> BaseSource:
       return MySource(api_key=src.get("api_key", ""))
   ```
3. **Register it** by appending a `(config_key, factory)` tuple to
   `_SOURCE_REGISTRY`:
   ```python
   ("myname", _make_myname),
   ```
4. **Add shorthand mappings** in `SRC_MAP` (shorthand to display name) and
   `SHORTHAND_TO_CFG_KEY` (shorthand to config key):
   ```python
   SRC_MAP["mysh"] = "My Source"
   SHORTHAND_TO_CFG_KEY["mysh"] = "myname"
   ```

### 4. Add tests

Create `tests/test_myname.py` (or add to `tests/test_sources.py` for simpler
sources). At minimum cover:

- Basic search returns `Paper` objects with correct fields
- `available()` returns `False` when required credentials are missing
- `filters.field == "title"` and `"abstract"` send the correct native query
- `filters.raw_query` is forwarded verbatim
- Year / author / journal filters are applied correctly

### 5. Update documentation

- Add the source to the table in `docs/guide/sources.md` with the source name,
  shorthand, coverage, and authentication requirements.
- Add the source to the table in `README.md` and `docs/guide/index.md`.

---

## Documentation

The documentation site is built with [VitePress](https://vitepress.dev/).

### Local preview

```bash
cd docs
npm install        # first time only
npm run docs:dev   # live-reload dev server at http://localhost:5173/mosaic/
```

### Build

```bash
cd docs
npm run docs:build   # output in docs/.vitepress/dist/
```

### Structure

- **`docs/guide/*.md`** — content pages (Markdown with VitePress extensions).
- **`docs/.vitepress/config.mts`** — nav and sidebar config; update this when
  adding a new page.
- **`docs/public/`** — static assets (coverage badge JSON, etc.).

### Writing style

- Write for a researcher who is comfortable with the command line but may not
  be a Python developer.
- Use second person ("you") and present tense.
- Code blocks must be runnable as-is — no `...` placeholders unless the
  surrounding text explains what to substitute.
- Keep headings short; use `###` for sub-sections within a page.

### Changelog

The changelog is maintained by `git-cliff` and **must not be edited by
hand**. After a release, regenerate it with:

```bash
git cliff -o CHANGELOG.md
{ printf -- "---\ntitle: Changelog\n---\n\n"; awk '/^## \[/{found=1} found' CHANGELOG.md; } \
  > docs/guide/changelog.md
```

---

## CI pipeline

Every push to `main` and every pull request runs the CI pipeline defined in
`.github/workflows/tests.yml`. It has three jobs:

| Job | Trigger | What it does |
|-----|---------|--------------|
| **Test & Coverage** | every push / PR | `pytest` on Python 3.11; writes coverage JSON to `docs/public/` |
| **Deploy Docs** | push to `main` only | builds VitePress, deploys to GitHub Pages |
| **Publish to PyPI** | version tag `v*` | builds wheel + sdist, publishes via OIDC Trusted Publisher |

**Your PR must pass the Test & Coverage job before it can be merged.**

The Deploy and Publish jobs do not run on PRs — they are triggered only by
merges to `main` and version tags respectively.

---

## Release process

Releases are managed by the maintainer using `release.sh`:

```bash
./release.sh --patch   # 1.2.3 -> 1.2.4
./release.sh --minor   # 1.2.3 -> 1.3.0
./release.sh --major   # 1.2.3 -> 2.0.0
./release.sh 2.5.0     # exact version
```

The script validates the working tree is clean, bumps the version in
`pyproject.toml` and `mosaic/__init__.py`, regenerates `CHANGELOG.md` via
`git-cliff`, commits, pushes the commit, then tags and pushes the tag.
The CI pipeline picks up the tag, builds the distribution, and publishes
to PyPI automatically via OIDC Trusted Publisher (no API token needed).

Semantic Versioning rules:
- `patch` — bug fixes only
- `minor` — new features, backwards-compatible
- `major` — breaking changes

---

## Questions?

Open a [discussion](https://github.com/szaghi/mosaic/discussions) for
questions that are not bug reports or feature requests. For quick questions
you can also open an issue with the **question** label.

---

*Thank you for contributing to MOSAIC!*
