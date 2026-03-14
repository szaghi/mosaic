"""Bridge between MOSAIC and Google NotebookLM via notebooklm-py."""

from __future__ import annotations

import logging
from pathlib import Path

from mosaic.models import Paper

log = logging.getLogger(__name__)

# NotebookLM enforces a hard cap of 50 sources per notebook.
_SOURCE_LIMIT = 50

# Mapping from flag name to artifacts client method name
_ARTIFACT_METHODS: dict[str, str] = {
    "podcast": "generate_audio",
    "video": "generate_video",
    "briefing": "generate_report",
    "study_guide": "generate_study_guide",
    "quiz": "generate_quiz",
    "flashcards": "generate_flashcards",
    "infographic": "generate_infographic",
    "slide_deck": "generate_slide_deck",
    "data_table": "generate_data_table",
    "mind_map": "generate_mind_map",
}


def _require_notebooklm() -> None:
    """Raise a clear ImportError if notebooklm-py is not installed."""
    try:
        import notebooklm  # noqa: F401
    except ImportError:
        raise ImportError(
            "notebooklm-py is not installed.\n"
            "Install it with:  pip install 'mosaic-search[notebooklm]'\n"
            "Then authenticate: notebooklm login"
        ) from None


def check_notebooklm_status() -> dict[str, object]:
    """Check NotebookLM availability and authentication status.

    Returns a dict with:
      - installed (bool): True if notebooklm-py is importable.
      - authenticated (bool): True if storage_state.json exists and is non-empty.
      - storage_path (str | None): Resolved path to storage_state.json.
      - auth_env (bool): True if NOTEBOOKLM_AUTH_JSON env var is set.
    """
    import os

    status: dict[str, object] = {
        "installed": False,
        "authenticated": False,
        "storage_path": None,
        "auth_env": bool(os.environ.get("NOTEBOOKLM_AUTH_JSON")),
    }

    try:
        import notebooklm  # noqa: F401

        status["installed"] = True
    except ImportError:
        return status

    try:
        from notebooklm.paths import get_storage_path

        sp = get_storage_path()
        status["storage_path"] = str(sp)
        if sp.exists() and sp.stat().st_size > 10:
            status["authenticated"] = True
    except Exception:
        log.debug("Could not check NotebookLM storage path", exc_info=True)

    # Auth via env var counts as authenticated
    if status["auth_env"]:
        status["authenticated"] = True

    return status


async def _generate_artifacts(client, nb_id: str, artifacts: set[str], added: int) -> None:
    """Queue artifact generation for *nb_id* based on the *artifacts* set."""
    if not artifacts or added == 0:
        return
    for flag, method_name in _ARTIFACT_METHODS.items():
        if flag in artifacts:
            method = getattr(client.artifacts, method_name, None)
            if method is not None:
                await method(nb_id)


async def create_notebook(
    name: str,
    papers_with_paths: list[tuple[Paper, Path | None]],
    artifacts: set[str] | None = None,
) -> str:
    """Create a NotebookLM notebook and populate it with papers.

    For each (paper, path) pair:
      - If *path* exists on disk  → uploads the local PDF file.
      - Else if paper.url is set  → adds the URL as a web source.
      - Otherwise                 → skipped.

    At most 50 sources are added (NotebookLM hard limit).
    *artifacts* is a set of flag names (e.g. {"podcast", "briefing"}) — any
    matching artifact generation is queued after import.

    Returns the new notebook ID.
    """
    from notebooklm import NotebookLMClient

    artifacts = artifacts or set()

    async with await NotebookLMClient.from_storage() as client:
        nb = await client.notebooks.create(name)
        nb_id = nb.id
        added = 0

        for paper, pdf_path in papers_with_paths:
            if added >= _SOURCE_LIMIT:
                break
            try:
                if pdf_path and pdf_path.exists():
                    await client.sources.add_file(nb_id, pdf_path)
                    added += 1
                elif paper.url:
                    await client.sources.add_url(nb_id, paper.url)
                    added += 1
            except Exception:
                log.debug("Failed to add source %s to notebook", paper.title, exc_info=True)

        await _generate_artifacts(client, nb_id, artifacts, added)

        return nb_id


async def create_notebook_from_dir(
    name: str,
    directory: Path,
    artifacts: set[str] | None = None,
) -> str:
    """Create a NotebookLM notebook from all PDFs in *directory*.

    PDFs are added in alphabetical order, up to the 50-source limit.
    *artifacts* is a set of flag names (e.g. {"podcast", "slide_deck"}) — any
    matching artifact generation is queued after import.

    Returns the new notebook ID.
    Raises ValueError if no PDFs are found in *directory*.
    """
    from notebooklm import NotebookLMClient

    artifacts = artifacts or set()
    pdfs = sorted(directory.glob("*.pdf"))
    if not pdfs:
        raise ValueError(f"No PDF files found in {directory}")

    async with await NotebookLMClient.from_storage() as client:
        nb = await client.notebooks.create(name)
        nb_id = nb.id
        added = 0

        for pdf in pdfs[:_SOURCE_LIMIT]:
            try:
                await client.sources.add_file(nb_id, pdf)
                added += 1
            except Exception:
                log.debug("Failed to add PDF %s to notebook", pdf.name, exc_info=True)

        await _generate_artifacts(client, nb_id, artifacts, added)

        return nb_id
