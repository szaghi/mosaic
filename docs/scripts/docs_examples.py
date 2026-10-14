"""Run the tutorial's commands and save what they print, for the pages to include.

Every step of the tutorial runs here, in order, in a scratch home directory (a fresh config, cache and library,
as a new user has). What a step prints is written to ``docs/examples/output/<chapter>/<name>.txt``, after the
command line as ``$ command``; the pages include these files, so the output on the pages is real.

The searches query the live sources, so the output changes as the literature does: run this when a chapter
changes, read the diff, and commit the files. The CI does not run it (no network in tests).

Environment:

``MOSAIC``             the ``mosaic`` to run (default: the one on PATH)
``MOSAIC_DOCS_EMAIL``  the e-mail sent to Unpaywall (required from chapter 4: Unpaywall rejects fake ones)
``MOSAIC_DOCS_PDF``    a PDF of the paper ``PAYWALLED_DOI``, "downloaded" in chapter 5's hand-off
``MOSAIC_DOCS_IMPORT`` a PDF of 10.1016/j.actaastro.2018.07.007, imported in chapter 5
``MOSAIC_DOCS_LLM``    ``base_url model embedding_model`` of an OpenAI-compatible server (chapters 8-10)

Usage::

    python docs/scripts/docs_examples.py                 # all chapters, in a new scratch home
    python docs/scripts/docs_examples.py --home DIR 04   # chapter 4 only, reusing DIR from an earlier run
    python docs/scripts/docs_examples.py --home DIR 10/top 08/compare   # single steps, in a home that has run
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "examples" / "output"
WIDTH = "120"

# the papers the tutorial follows
QUERY = "hall thruster particle-in-cell"
GET_DOI = "10.3389/fphy.2019.00140"  # open access (Frontiers)
SHOW_DOI = "10.3390/aerospace10010044"  # open access, but MDPI refuses scripted downloads
PAYWALLED_DOI = "10.1016/j.paerosci.2006.01.001"  # Elsevier: no open copy
HANDOFF_NAME = "1-s2.0-S0376042106000029-main.pdf"  # ScienceDirect's name for PAYWALLED_DOI
IMPORT_NAME = (
    "1-s2.0-S0094576517312663-main.pdf"  # ScienceDirect's name for 10.1016/j.actaastro.2018.07.007
)
SIMILAR_DOI = "10.1063/1.4972269"  # Boeuf, Tutorial: Physics and modeling of Hall thrusters

REFS_BIB = """\
@article{boeuf2017,
  author = {Boeuf, Jean-Pierre},
  title  = {Tutorial: Physics and modeling of Hall thrusters},
  doi    = {10.1063/1.4972269},
}
@article{taccogna2019,
  author = {Taccogna, Francesco and Garrigues, Laurent},
  title  = {Latest progress in Hall thrusters plasma modelling},
  doi    = {10.1007/s41614-019-0033-1},
}
"""


@dataclass
class Step:
    name: str  # output file stem; "" for a setup step, whose output is not kept
    cmd: str
    timeout: int = 600
    prelude: str = ""  # shell run first, not shown (e.g. a stand-in for the user's browser)
    trim: tuple[int, int] | None = None  # keep the first and last lines of a long output


# No browser opens while the docs are captured: hand-off "opens" the page with `true`.
def _no_browser(env: dict[str, str]) -> dict[str, str]:
    path = ":".join(d for d in env["PATH"].split(":") if not d.startswith("/mnt/"))
    return {"BROWSER": "true", "PATH": path}


def chapters(env: dict[str, str]) -> dict[str, list[Step]]:
    llm = env.get("MOSAIC_DOCS_LLM", "").split()
    base_url, model, embed = llm if len(llm) == 3 else ("", "", "")
    return {
        "01": [
            Step("version", "mosaic --version"),
            Step("search", f'mosaic search "{QUERY}" --max 5', trim=(26, 6)),
            Step("verbose", f'mosaic --verbose search "{QUERY}" --max 5 2>&1 | grep Warning'),
        ],
        "02": [
            Step("source", f'mosaic search "{QUERY}" --source arxiv --year 2020-2025'),
            Step(
                "field",
                'mosaic search "hall thruster" --field title --source oa --max 8 --sort citations',
            ),
            Step("author", 'mosaic search "hall thruster" --author Boeuf --source oa --max 25'),
            Step(
                "oa",
                'mosaic search "hall thruster anomalous transport" --oa-only --pdf-only --max 3',
            ),
            Step(
                "stats",
                'mosaic search "hall thruster anomalous transport" --max 5 --stats',
                trim=(21, 1),
            ),
        ],
        "03": [
            Step("stats", "mosaic cache stats"),
            Step(
                "cached", 'mosaic search "thruster simulation" --cached --sort year', trim=(14, 2)
            ),
            Step("list", "mosaic cache list -n 5"),
            Step("show", f"mosaic cache show {SHOW_DOI}"),
        ],
        "04": [
            Step("", f"mosaic config --unpaywall-email {env.get('MOSAIC_DOCS_EMAIL', '')}"),
            Step("download", f'mosaic search "{QUERY}" --source arxiv --max 3 --download'),
            Step("get", f"mosaic get {GET_DOI}"),
            Step("blocked", f"mosaic get {SHOW_DOI}"),
            Step("ls", "ls ~/mosaic-papers"),
            Step("", f"cat > refs.bib <<'EOF'\n{REFS_BIB}EOF"),
            Step("bulk", "mosaic get --from refs.bib"),
            Step("verify", "mosaic cache verify"),
        ],
        "05": [
            Step("get", f"mosaic get {PAYWALLED_DOI}"),
            Step("auth", "mosaic auth status"),
            Step("", "mkdir -p ~/Downloads"),
            Step(
                "handoff",
                f"mosaic get {PAYWALLED_DOI} --handoff --watch-dir ~/Downloads",
                # the user clicks "Download PDF" in their browser, a few seconds later
                prelude=f"(sleep 6; cp '{env.get('MOSAIC_DOCS_PDF', '')}' ~/Downloads/{HANDOFF_NAME}) &",
            ),
            Step("", f"cp '{env.get('MOSAIC_DOCS_IMPORT', '')}' ~/Downloads/{IMPORT_NAME}"),
            Step("import", f"mosaic import ~/Downloads/{IMPORT_NAME}"),
            Step("ls", "ls ~/Downloads ~/mosaic-papers"),
        ],
        "06": [
            Step(
                "output",
                f'mosaic search "{QUERY}" --cached --output refs.bib --output refs.csv',
                trim=(6, 4),
            ),
            Step("bib", "head -n 14 refs.bib"),
            Step("cite", f"mosaic cite {GET_DOI} --style apa"),
            Step(
                "json",
                f'mosaic search "{QUERY}" --cached --json | jq -r \'.papers[] | "\\(.year)  \\(.doi)"\' | head -n 5',
            ),
            Step("", "mosaic config --obsidian-vault ~/vault"),
            Step("obsidian", f'mosaic search "{QUERY}" --cached --obsidian', trim=(6, 3)),
            Step("note", "ls ~/vault/papers | head -n 3"),
        ],
        "07": [
            Step("similar", f"mosaic similar {SIMILAR_DOI} --max 8"),
            Step(
                "add",
                'mosaic watch add "hall thruster anomalous transport" --name hall-transport --source arxiv',
            ),
            Step("list", "mosaic watch list"),
            Step("run", "mosaic watch run"),
        ],
        "08": [
            Step("bm25", 'mosaic search "electron transport" --cached --sort relevance'),
            Step(
                "",
                f"mosaic config --llm-provider openai --llm-base-url {base_url} --llm-api-key ollama "
                f"--llm-model {model} --llm-timeout 900",
            ),
            Step(
                "summarise",
                'mosaic search "hall thruster anomalous electron transport" --source arxiv --max 6 --summarise',
                timeout=1800,
            ),
            Step(
                "compare",
                'mosaic compare --query "hall thruster" -n 4 --dimensions "method,dimensionality,key finding"',
                timeout=1800,
            ),
        ],
        "09": [
            Step(
                "",
                f"mosaic config --embedding-model {embed} --embedding-base-url {base_url} --embedding-api-key ollama",
            ),
            Step("index", "mosaic index", timeout=1800),
            Step("semantic", 'mosaic search "electrons crossing the magnetic field" --semantic'),
            Step(
                "ask",
                'mosaic ask "What causes anomalous electron transport in Hall thrusters?" --show-sources',
                timeout=1800,
            ),
        ],
        "10": [
            Step("enrich", "mosaic index --enrich-citations", timeout=1800),
            Step("top", "mosaic network --top 5"),
            Step(
                "cluster", 'mosaic network --query "thruster" --cluster --top 3 --output graph.json'
            ),
        ],
    }


def normalise(text: str, home: str) -> str:
    text = text.replace(home, "~")
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)  # stray escape codes
    return "\n".join(line.rstrip() for line in text.splitlines()).strip("\n") + "\n"


_ROW = re.compile(r"^ \d+\s")  # the first line of a row of a results table


def trimmed(text: str, keep: tuple[int, int] | None) -> str:
    """Keep about *keep* = (head, tail) lines, cutting only between table rows."""
    lines = text.splitlines()
    if not keep or len(lines) <= sum(keep) + 1:
        return text
    head, tail = keep
    start = len(lines) - tail
    if any(_ROW.match(line) for line in lines):
        while head < start and not _ROW.match(lines[head]):  # finish the row in progress
            head += 1
        while (
            start < len(lines) - 1 and not _ROW.match(lines[start]) and lines[start].startswith(" ")
        ):
            start += 1  # do not start inside a row
    cut = start - head
    return "\n".join([*lines[:head], f"  ⋮  ({cut} lines not shown)", *lines[start:]]) + "\n"


def run(step: Step, home: Path, env: dict[str, str]) -> str:
    script = f"{step.prelude}\n{step.cmd}" if step.prelude else step.cmd
    if "--handoff" in step.cmd:
        env = {**env, **_no_browser(env)}
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=home,
        env=env,
        capture_output=True,
        text=True,
        timeout=step.timeout,
        check=False,
    )
    return proc.stdout + proc.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "chapters", nargs="*", help="chapters (04) or steps (04/get) to run (default: all)"
    )
    parser.add_argument(
        "--home", type=Path, help="scratch home to use or reuse (default: a new one)"
    )
    args = parser.parse_args()

    home = (args.home or Path(tempfile.mkdtemp(prefix="mosaic-docs-"))).resolve()
    home.mkdir(parents=True, exist_ok=True)
    mosaic = shutil.which(os.environ.get("MOSAIC", "mosaic"))
    if not mosaic:
        sys.exit("mosaic not found: set MOSAIC")
    bindir = home / ".bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "mosaic").unlink(missing_ok=True)
    (bindir / "mosaic").symlink_to(mosaic)
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "COLUMNS": WIDTH,
        "NO_COLOR": "1",
        "TERM": "dumb",
    }
    print(f"home: {home}")
    selected = args.chapters or None
    for chapter, steps in chapters(env).items():
        if (
            selected
            and chapter not in selected
            and not any(s.startswith(chapter + "/") for s in selected)
        ):
            continue
        for step in steps:
            if selected and chapter not in selected and f"{chapter}/{step.name}" not in selected:
                continue  # single steps run alone: no setup steps, the home has them already
            print(f"[{chapter}] {step.cmd.splitlines()[0]}", flush=True)
            out = run(step, home, env)
            if step.name:
                path = OUTPUT / chapter / f"{step.name}.txt"
                path.parent.mkdir(parents=True, exist_ok=True)
                text = normalise(f"$ {step.cmd}\n{out}", str(home))
                path.write_text(trimmed(text, step.trim))
    return 0


if __name__ == "__main__":
    sys.exit(main())
