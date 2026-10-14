---
title: Contributing
---

# Contributing

Bug reports, source requests and pull requests go to [GitHub](https://github.com/szaghi/mosaic/issues). For a bug,
give `mosaic --version`, the exact command, and its full output (run it with `mosaic --verbose ...` to include the
per-source warnings). [Architecture](/guide/architecture) explains how the code is organised.

## Setup

```bash
git clone https://github.com/szaghi/mosaic.git
cd mosaic
make dev      # creates .venv and installs mosaic in editable mode with the dev extras
```

Use `.venv/bin/mosaic` to run your working copy. For the optional features, install their extras into the same
environment: `.venv/bin/pip install -e ".[dev,rag,analysis,ui,browser]"`.

| Command | Does |
|---|---|
| `make test` | the test suite with coverage |
| `make lint` | `ruff check` and `ruff format --check` on `mosaic/`, `tests/` and `docs/scripts/` (no changes) |
| `make fmt` | fixes what Ruff can and formats |
| `.venv/bin/pytest tests/test_db.py::TestGetByDois` | one test class |

Tests never touch the network: they patch `httpx` and the other I/O with `unittest.mock`, and `conftest.py`
provides `tmp_cache` (an in-memory cache), `paper` and `make_response()`. A change comes with the test that shows
it working. A test that needs an optional package skips itself when the package is missing; the CI installs the
`dev`, `ui` and `rag` extras.

## Commits

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): subject`,
lowercase, imperative, no final period, for example `fix(cli): keep long paths on one line`. The type decides the
changelog section (`feat` Added, `fix` Fixed, `perf` Performance, `refactor` Changed, `docs` Documentation;
`test`, `chore`, `ci` are left out), and the CI checks pull request titles the same way. Mark a breaking change
with `!` after the type and a `BREAKING CHANGE:` footer.

## Documentation

The site is VitePress, in `docs/`:

```bash
cd docs
npm install
npm run docs:dev       # http://localhost:5173/mosaic/, reloading as you edit
npm run docs:build
```

Three scripts in `docs/scripts/` keep it true to the code:

| Script | Does | When |
|---|---|---|
| `gen_cli_reference.py` | rewrites the generated part of `docs/reference/*.md` from the command line | after changing a command or an option |
| `check_doc_commands.py` | checks that every `mosaic ...` command written in the docs exists, with its options | any time |
| `docs_examples.py` | runs the tutorial's commands in a scratch home and saves their output to `docs/examples/output/` | after changing a tutorial chapter or the output of a command it shows |

```bash
.venv/bin/python docs/scripts/gen_cli_reference.py
.venv/bin/python docs/scripts/check_doc_commands.py
MOSAIC=$PWD/.venv/bin/mosaic MOSAIC_DOCS_EMAIL=you@university.edu .venv/bin/python docs/scripts/docs_examples.py
```

`tests/test_docs.py` runs the first two in check mode, so a stale reference or a wrong command fails the tests.
`docs_examples.py` queries the live sources and is not run by the CI: read the diff of the outputs before
committing them. Its docstring lists the environment variables the later chapters need (a PDF to import, a local
LLM).

Do not edit `CHANGELOG.md` or `docs/guide/changelog.md`: git-cliff writes them at release time.

## Releases

The maintainer releases from `main`:

```bash
./release.sh --patch     # or --minor, --major, or an explicit X.Y.Z
```

The script stops unless the tree is clean, `main` is up to date with `origin`, the tag is free, git-cliff is
installed and the lint passes. After a confirmation it bumps the version in `pyproject.toml` and
`mosaic/__init__.py`, regenerates both changelogs, runs the tests, commits, creates the annotated tag `vX.Y.Z`
and pushes with `--follow-tags`. If a stage fails, it prints the commands that resume from there. The tag starts
the CI job that builds the package and publishes it to PyPI (trusted publishing, no token); the Build workflow
attaches the standalone apps to the GitHub release.

A new command or option is a minor release; a fix is a patch.
