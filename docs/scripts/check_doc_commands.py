"""Check every ``mosaic`` command written in the documentation against the real command line.

A command is a line of a fenced code block (``$ `` prompt allowed, ``\\`` continuations joined) or an inline code
span that starts with ``mosaic``. Its subcommands must exist, and so must every option it names (``--opt`` or
``--opt=value``): the documentation once showed ``mosaic config --set``, an option that never existed. Values and
placeholders are not checked; neither are the changelog (history) and the social posts.

Usage::

    python docs/scripts/check_doc_commands.py        # report, exit 1 when a command is wrong
"""

from __future__ import annotations

import re
import shlex
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import click
import typer.main

from mosaic.cli import app

DOCS = Path(__file__).resolve().parent.parent
SKIPPED = ("guide/changelog.md", "node_modules", ".vitepress", "social/")
_FENCE = re.compile(r"^\s*(```+|~~~+)")
_INLINE = re.compile(r"(?<!`)`(mosaic [^`]+)`(?!`)")
_STOP = {"|", "||", "&&", ";", ">", ">>", "2>", "2>&1", "<", "&"}


@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    command: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}: {self.command}"


def commands(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line, command)`` for each ``mosaic`` command in a Markdown page."""
    fence = False
    pending, start = "", 0
    for n, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            fence, pending = not fence, ""
            continue
        if fence:
            body = line.strip()
            body = body[2:] if body.startswith("$ ") else body
            if pending:
                body = pending + " " + body
            else:
                start = n
            if body.endswith("\\"):
                pending = body[:-1].strip()
                continue
            pending = ""
            if body.startswith("mosaic ") or body == "mosaic":
                yield start, body
        else:
            for m in _INLINE.finditer(line):
                yield n, m.group(1)


def _tokens(command: str) -> list[str]:
    command = re.sub(r"\s#.*$", "", command)
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for i, tok in enumerate(tokens):
        if tok in _STOP:
            return tokens[:i]
    return tokens


def _known(cmd: click.Command, token: str) -> bool:
    name = token.split("=")[0]
    if name == "--help":
        return True
    return any(name in p.opts or name in getattr(p, "secondary_opts", []) for p in cmd.params)


def check(command: str, root: click.Group) -> str | None:
    """Return what is wrong with *command*, or None."""
    tokens = _tokens(command)
    cmd: click.Command = root
    k = 1
    while isinstance(cmd, click.Group):
        # global options come before the command
        while k < len(tokens) and tokens[k].startswith("-"):
            if not _known(cmd, tokens[k]):
                return f"unknown option {tokens[k].split('=')[0]}"
            k += 1
        if k >= len(tokens) or tokens[k] in ("...", "COMMAND", "[OPTIONS]"):
            return None
        if tokens[k] not in cmd.commands:
            return f"unknown command {tokens[k]!r}"
        cmd = cmd.commands[tokens[k]]
        k += 1
    for tok in tokens[k:]:
        if tok == "--":
            break
        if (
            tok.startswith("-")
            and len(tok) > 1
            and not re.match(r"^-\d", tok)
            and not _known(cmd, tok)
        ):
            return f"unknown option {tok.split('=')[0]}"
    return None


def problems() -> list[Problem]:
    root = typer.main.get_command(app)
    found = []
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(DOCS).as_posix()
        if any(s in rel for s in SKIPPED):
            continue
        for line, command in commands(path.read_text()):
            message = check(command, root)
            if message:
                found.append(Problem(rel, line, command, message))
    return found


def main() -> int:
    found = problems()
    for p in found:
        print(p)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
