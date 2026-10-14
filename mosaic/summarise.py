"""LLM synthesis of a search result list (``mosaic search --summarise``, issue #14).

Unlike ``mosaic ask``, this needs no vector index: it summarises the papers
just returned, in the order they are displayed, so ``[n]`` citations in the
summary match the row numbers of the results table.
"""

from __future__ import annotations

from mosaic import llm
from mosaic.models import Paper

# Bounds the prompt to roughly 10k tokens regardless of --max.
MAX_PAPERS = 40
ABSTRACT_CHARS = 1000

_PROMPT = """\
You are summarising the results of a literature search for: {query!r}

Below are {n} papers, numbered as they appear in the user's results table.{truncated}

Write ONE paragraph of at most 150 words that synthesises the main themes,
methods, and how the work has evolved across the years covered. Cite papers
inline as [n] using the numbers given. Use only the information below: do not
add findings, numbers, or claims that are not stated in the titles or
abstracts. Papers marked "(no abstract)" may be cited for their title only.

{papers}
"""


def build_prompt(query: str, papers: list[Paper]) -> str:
    """Build the synthesis prompt for the first ``MAX_PAPERS`` of *papers*."""
    shown = papers[:MAX_PAPERS]
    blocks = []
    for i, p in enumerate(shown, 1):
        year = p.year or "n.d."
        abstract = (p.abstract or "").strip()
        if len(abstract) > ABSTRACT_CHARS:
            abstract = abstract[:ABSTRACT_CHARS].rsplit(" ", 1)[0] + " ..."
        blocks.append(f"[{i}] {p.title} ({year})\n{abstract or '(no abstract)'}")
    truncated = (
        f" Only the first {len(shown)} of {len(papers)} results are included."
        if len(papers) > len(shown)
        else ""
    )
    return _PROMPT.format(
        query=query, n=len(shown), truncated=truncated, papers="\n\n".join(blocks)
    )


def summarise(query: str, papers: list[Paper], cfg: dict) -> str | None:
    """Return a one-paragraph synthesis of *papers*, or None if none has an abstract.

    A summary of titles alone would be mostly invented, so it is not attempted.

    Raises
    ------
    mosaic.llm.LLMConfigError
        If no LLM is configured.
    httpx.HTTPError
        If the LLM request fails.
    """
    if not any(p.abstract for p in papers[:MAX_PAPERS]):
        return None
    return llm.complete(build_prompt(query, papers), cfg, max_tokens=600).strip()
