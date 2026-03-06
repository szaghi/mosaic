"""Bridge between MOSAIC and Google NotebookLM via notebooklm-py."""
from __future__ import annotations

from pathlib import Path

from mosaic.models import Paper

# NotebookLM enforces a hard cap of 50 sources per notebook.
_SOURCE_LIMIT = 50


def _require_notebooklm() -> None:
    """Raise a clear ImportError if notebooklm-py is not installed."""
    try:
        import notebooklm  # noqa: F401
    except ImportError:
        raise ImportError(
            "notebooklm-py is not installed.\n"
            "Install it with:  pip install 'mosaic-search[notebooklm]'\n"
            "Then authenticate: notebooklm login"
        )


async def create_notebook(
    name: str,
    papers_with_paths: list[tuple[Paper, Path | None]],
    generate_podcast: bool = False,
) -> str:
    """Create a NotebookLM notebook and populate it with papers.

    For each (paper, path) pair:
      - If *path* exists on disk  → uploads the local PDF file.
      - Else if paper.url is set  → adds the URL as a web source.
      - Otherwise                 → skipped.

    At most 50 sources are added (NotebookLM hard limit).
    If *generate_podcast* is True, an Audio Overview is queued after import.

    Returns the new notebook ID.
    """
    from notebooklm import NotebookLMClient

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
                pass  # individual source failures are non-fatal

        if generate_podcast and added > 0:
            await client.artifacts.generate_audio(nb_id)

        return nb_id


async def create_notebook_from_dir(
    name: str,
    directory: Path,
    generate_podcast: bool = False,
) -> str:
    """Create a NotebookLM notebook from all PDFs in *directory*.

    PDFs are added in alphabetical order, up to the 50-source limit.
    If *generate_podcast* is True, an Audio Overview is queued after import.

    Returns the new notebook ID.
    Raises ValueError if no PDFs are found in *directory*.
    """
    from notebooklm import NotebookLMClient

    pdfs = sorted(directory.glob("*.pdf"))
    if not pdfs:
        raise ValueError(f"No PDF files found in {directory}")

    async with await NotebookLMClient.from_storage() as client:
        nb = await client.notebooks.create(name)
        nb_id = nb.id

        for pdf in pdfs[:_SOURCE_LIMIT]:
            try:
                await client.sources.add_file(nb_id, pdf)
            except Exception:
                pass

        if generate_podcast:
            await client.artifacts.generate_audio(nb_id)

        return nb_id
