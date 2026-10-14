# Contributing to MOSAIC

Bug reports, feature requests, new sources, documentation and code fixes are all welcome. The full guide, kept
current with the code, is on the documentation site:
**[Contributing](https://szaghi.github.io/mosaic/guide/contributing)**, with
[Architecture](https://szaghi.github.io/mosaic/guide/architecture) for how the code is organised.

## Code of Conduct

This project follows the
[Contributor Covenant Code of Conduct v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
In short: be kind, be respectful, and assume good faith. Harassment of any kind will not be tolerated.

Violations can be reported to the maintainer at **stefano.zaghi@gmail.com**. All reports will be kept
confidential.

## Reporting a bug

Search the [open issues](https://github.com/szaghi/mosaic/issues) first, then
[open one](https://github.com/szaghi/mosaic/issues/new?template=bug_report.md) with `mosaic --version`, your
Python version and operating system, the exact command, and its full output (run it as `mosaic --verbose ...` to
include the per-source warnings).

For a feature, [open a request](https://github.com/szaghi/mosaic/issues/new?template=feature_request.md) and
describe the use case, not only the solution.

## In short

```bash
git clone https://github.com/szaghi/mosaic && cd mosaic
make dev        # .venv with mosaic in editable mode and the dev tools
make test       # tests never touch the network
make lint       # ruff check + format --check
```

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`fix(cli): ...`); pull
request titles are checked the same way. A change comes with the test that shows it working, and with its
documentation: `python docs/scripts/gen_cli_reference.py` after changing a command or an option.
