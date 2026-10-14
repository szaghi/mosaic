"""The documentation matches the command line: generated reference current, every written command valid."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import typer.main

from mosaic.cli import app

SCRIPTS = Path(__file__).resolve().parent.parent / "docs" / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up there
    spec.loader.exec_module(module)
    return module


def test_command_reference_is_current():
    gen = _load("gen_cli_reference")
    stale = [
        str(path.relative_to(gen.REFERENCE.parent))
        for path, text in gen.pages().items()
        if not path.exists() or path.read_text() != text
    ]
    assert not stale, f"run python docs/scripts/gen_cli_reference.py: {stale}"


def test_documented_commands_exist():
    found = _load("check_doc_commands").problems()
    assert not found, "\n".join(str(p) for p in found)


def test_checker_flags_unknown_options_and_commands():
    check = _load("check_doc_commands")
    root = typer.main.get_command(app)
    assert check.check("mosaic config --set a=b", root) == "unknown option --set"
    assert check.check("mosaic serach x", root) == "unknown command 'serach'"
    assert check.check("mosaic --verbose search x --max 5 | head", root) is None
    assert check.check("mosaic cache list -n 5", root) is None
