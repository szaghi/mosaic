PIPX_PY := $(HOME)/.local/share/pipx/venvs/mosaic-search/bin/python

.PHONY: dev test

# Reinstall from local source into the pipx venv (keeps pipx upgrade working).
dev:
	$(PIPX_PY) -m pip install --no-deps -q .
	@echo "mosaic updated from source"

# Run the test suite
test:
	.venv/bin/pytest
