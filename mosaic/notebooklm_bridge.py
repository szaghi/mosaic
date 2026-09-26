"""Bridge between MOSAIC and Google NotebookLM via notebooklm-py."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
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


@dataclass
class NotebookResult:
    """Outcome of a notebook creation, including what did *not* happen."""

    nb_id: str
    sources_added: int = 0
    sources_failed: list[str] = field(default_factory=list)
    artifacts_queued: list[str] = field(default_factory=list)
    artifacts_failed: list[str] = field(default_factory=list)
    # Requested artifacts that were not queued because the notebook is empty
    artifacts_skipped: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://notebooklm.google.com/notebook/{self.nb_id}"

    def warnings(self) -> list[str]:
        """Human-readable warnings for everything that did not go as requested."""
        out: list[str] = []
        if self.sources_added == 0:
            out.append("No sources could be added: the notebook is empty.")
        if self.sources_failed:
            out.append(f"{len(self.sources_failed)} source(s) could not be added.")
        if self.artifacts_skipped:
            out.append(
                "Artifacts not queued because the notebook has no sources: "
                + ", ".join(self.artifacts_skipped)
                + "."
            )
        if self.artifacts_failed:
            out.append("Artifacts that failed to queue: " + ", ".join(self.artifacts_failed) + ".")
        return out


_LOGIN_HINT = (
    "Run `notebooklm login` (requires `pip install 'notebooklm-py[browser]'`) "
    "or set the NOTEBOOKLM_AUTH_JSON environment variable."
)


def require_notebooklm() -> None:
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


def preflight_error() -> str | None:
    """Return a user-facing message when NotebookLM cannot be used, else ``None``."""
    status = check_notebooklm_status()
    if not status["installed"]:
        return (
            "notebooklm-py is not installed. "
            "Install it with: pip install 'mosaic-search[notebooklm]'"
        )
    if not status["authenticated"]:
        return f"NotebookLM is not authenticated. {_LOGIN_HINT}"
    return None


def describe_error(exc: BaseException) -> str:
    """Map exceptions raised by notebooklm-py to actionable messages."""
    if isinstance(exc, ImportError):
        return str(exc)
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, FileNotFoundError) or any(
        hint in lowered for hint in ("storage", "login", "authenticat", "cookie", "401", "403")
    ):
        return f"NotebookLM authentication failed ({text or type(exc).__name__}). {_LOGIN_HINT}"
    return f"NotebookLM error: {text or type(exc).__name__}"


async def _open_client():
    """Return an async context manager for an authenticated NotebookLM client.

    notebooklm-py < 0.8 exposes ``from_storage()`` as a coroutine that returns
    the client; newer releases return a context object meant for ``async with``
    directly (awaiting it is deprecated and removed in 1.0).
    """
    from notebooklm import NotebookLMClient

    ctx = NotebookLMClient.from_storage()
    if not hasattr(ctx, "__aenter__"):
        ctx = await ctx
    return ctx


async def _generate_artifacts(
    client, nb_id: str, artifacts: set[str], added: int, result: NotebookResult
) -> None:
    """Queue artifact generation for *nb_id* and record the outcome in *result*."""
    if not artifacts:
        return
    requested = [flag for flag in _ARTIFACT_METHODS if flag in artifacts]
    unknown = sorted(artifacts - set(_ARTIFACT_METHODS))
    result.artifacts_failed.extend(unknown)
    if added == 0:
        # NotebookLM cannot generate anything from an empty notebook
        result.artifacts_skipped.extend(requested)
        return
    for flag in requested:
        method = getattr(client.artifacts, _ARTIFACT_METHODS[flag], None)
        if method is None:
            result.artifacts_failed.append(flag)
            continue
        try:
            await method(nb_id)
            result.artifacts_queued.append(flag)
        except Exception:
            log.warning("Failed to queue artifact %s for notebook %s", flag, nb_id, exc_info=True)
            result.artifacts_failed.append(flag)


async def create_notebook(
    name: str,
    papers_with_paths: list[tuple[Paper, Path | None]],
    artifacts: set[str] | None = None,
) -> NotebookResult:
    """Create a NotebookLM notebook and populate it with papers.

    For each (paper, path) pair:
      - If *path* exists on disk  → uploads the local PDF file.
      - Else if paper.url is set  → adds the URL as a web source.
      - Otherwise                 → skipped.

    At most 50 sources are added (NotebookLM hard limit).
    *artifacts* is a set of flag names (e.g. {"podcast", "briefing"}) — any
    matching artifact generation is queued after import.

    Returns a :class:`NotebookResult` describing sources and artifacts.
    """
    artifacts = artifacts or set()

    async with await _open_client() as client:
        nb = await client.notebooks.create(name)
        result = NotebookResult(nb_id=nb.id)

        for paper, pdf_path in papers_with_paths:
            if result.sources_added >= _SOURCE_LIMIT:
                break
            try:
                if pdf_path and pdf_path.exists():
                    await client.sources.add_file(result.nb_id, pdf_path)
                    result.sources_added += 1
                elif paper.url:
                    await client.sources.add_url(result.nb_id, paper.url)
                    result.sources_added += 1
            except Exception:
                log.warning("Failed to add source %s to notebook", paper.title, exc_info=True)
                result.sources_failed.append(paper.title)

        await _generate_artifacts(client, result.nb_id, artifacts, result.sources_added, result)

        return result


async def create_notebook_from_dir(
    name: str,
    directory: Path,
    artifacts: set[str] | None = None,
) -> NotebookResult:
    """Create a NotebookLM notebook from all PDFs in *directory*.

    PDFs are added in alphabetical order, up to the 50-source limit.
    *artifacts* is a set of flag names (e.g. {"podcast", "slide_deck"}) — any
    matching artifact generation is queued after import.

    Returns a :class:`NotebookResult` describing sources and artifacts.
    Raises ValueError if no PDFs are found in *directory*.
    """
    artifacts = artifacts or set()
    pdfs = sorted(directory.glob("*.pdf"))
    if not pdfs:
        raise ValueError(f"No PDF files found in {directory}")

    async with await _open_client() as client:
        nb = await client.notebooks.create(name)
        result = NotebookResult(nb_id=nb.id)

        for pdf in pdfs[:_SOURCE_LIMIT]:
            try:
                await client.sources.add_file(result.nb_id, pdf)
                result.sources_added += 1
            except Exception:
                log.warning("Failed to add PDF %s to notebook", pdf.name, exc_info=True)
                result.sources_failed.append(pdf.name)

        await _generate_artifacts(client, result.nb_id, artifacts, result.sources_added, result)

        return result
