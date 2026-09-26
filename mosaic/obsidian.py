"""Obsidian vault integration — write paper notes as Obsidian-compatible Markdown.

Each paper is written as a separate ``.md`` file with:

* **YAML frontmatter** — Obsidian properties (title, authors, year, DOI …)
  compatible with the *Properties* core plugin, *Dataview*, *Templater*, and
  the *Templates* core plugin.
* **Callout block** — abstract rendered as ``> [!abstract]``.
* **Metadata table** — human-readable field/value table.
* **See also** — ``[[wikilinks]]`` to other papers exported in the same batch
  (when ``wikilinks=True`` in the config).

Templates / Templater compatibility
------------------------------------
Generated notes contain no ``{{…}}`` or ``<%…%>`` template syntax.  They are
safe to open in a vault that uses either the *Templates* core plugin or the
*Templater* community plugin; neither plugin will attempt to process a note
that contains no template variables.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from mosaic.models import Paper

# ── minimal YAML serialiser (no external dependency) ─────────────────────────


def _yaml_str(s: str) -> str:
    """Return a YAML-safe scalar representation of *s*.

    Quotes the string when it contains characters that would be misinterpreted
    by YAML parsers or by Obsidian's property reader.

    Args:
        s: The raw string value.

    Returns:
        A YAML scalar — either the bare string or a double-quoted string with
        backslash-escaped special characters.
    """
    need_quote = (
        not s
        or s[0] in "-?:,[]{}#&*!|>'\"%@`"
        or any(c in s for c in ":#{}[]\n\r")
        or s != s.strip()
    )
    if need_quote:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "")
        return f'"{escaped}"'
    return s


def _frontmatter(data: dict) -> str:
    """Serialise *data* as a YAML frontmatter block.

    Handles strings, integers, booleans, and lists of strings.  Does not
    depend on PyYAML or any external library.

    Args:
        data: Ordered dict of frontmatter key/value pairs.

    Returns:
        A string of the form ``---\\n…\\n---`` ready to prepend to a note.
    """
    lines: list[str] = ["---"]
    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, int):
            lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_yaml_str(str(item))}")
        else:
            lines.append(f"{key}: {_yaml_str(str(value))}")
    lines.append("---")
    return "\n".join(lines)


def _read_frontmatter(path: Path) -> dict[str, str]:
    """Return the top-level scalar properties of a note's YAML frontmatter.

    Only understands what :func:`_frontmatter` writes (bare or double-quoted
    scalars); lists and nested values are ignored.  Unreadable files and notes
    without frontmatter yield an empty dict.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    props: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_][\w-]*):\s?(.*)$", line)
        if not m:
            continue
        value = m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        props[m.group(1)] = value
    return props


def _note_is_for(path: Path, paper: Paper) -> bool:
    """True if the existing note at *path* describes *paper* (by DOI, arXiv ID or title)."""
    props = _read_frontmatter(path)
    if paper.doi and props.get("doi"):
        return props["doi"].lower() == paper.doi.lower()
    if paper.arxiv_id and props.get("arxiv_id"):
        return props["arxiv_id"].lower() == paper.arxiv_id.lower()

    def _norm(s: str) -> str:
        return " ".join(s.lower().split())

    return bool(props.get("title")) and _norm(props["title"]) == _norm(paper.title or "")


# ── main class ────────────────────────────────────────────────────────────────


class ObsidianVault:
    """Write MOSAIC search results as Obsidian-compatible paper notes.

    Each paper becomes one ``.md`` file inside the vault.  Notes are never
    overwritten — a paper whose note already exists is silently skipped,
    preserving any manual edits the user may have made.  If the filename is
    taken by a *different* paper's note (or a note of the user's own), the new
    note gets a short uid-derived suffix instead.

    The generated format is compatible with:

    * Obsidian *Properties* (YAML frontmatter key/value display)
    * *Dataview* community plugin (query by ``year``, ``doi``, etc.)
    * *Templates* core plugin (notes contain no ``{{…}}`` variables)
    * *Templater* community plugin (notes contain no ``<%…%>`` syntax)
    """

    def __init__(
        self,
        vault_path: str | Path,
        subfolder: str = "papers",
        filename_pattern: str = "{year}_{author}_{title}",
        tags: list[str] | None = None,
        wikilinks: bool = True,
    ) -> None:
        """Initialise the Obsidian vault integration.

        Args:
            vault_path: Absolute (or ``~``-prefixed) path to the Obsidian
                vault root directory.
            subfolder: Subfolder within the vault where paper notes are
                stored.  Pass an empty string to write notes to the vault
                root.
            filename_pattern: Pattern for the note filename (no extension).
                Supports the same placeholders as the PDF filename pattern:
                ``{year}``, ``{author}``, ``{title}``, ``{source}``,
                ``{doi}``, ``{journal}``.  Default:
                ``"{year}_{author}_{title}"``.
            tags: List of Obsidian tags to add to every note's frontmatter.
                Defaults to ``["paper"]``.
            wikilinks: When ``True`` (the default), a **See also** section
                with ``[[wikilinks]]`` is appended to each note, linking to
                the other papers exported in the same ``export_papers()`` call.
        """
        self._vault = Path(vault_path).expanduser()
        self._subfolder = subfolder
        self._pattern = filename_pattern
        self._tags = list(tags) if tags else ["paper"]
        self._wikilinks = wikilinks

    # ── public helpers ────────────────────────────────────────────────────────

    @property
    def notes_dir(self) -> Path:
        """Absolute path to the directory where notes are written."""
        return self._vault / self._subfolder if self._subfolder else self._vault

    def note_stem(self, paper: Paper) -> str:
        """Return the note filename stem (without ``.md`` extension) for *paper*.

        Reuses :meth:`~mosaic.models.Paper.safe_filename` for consistent
        slug generation; the ``.pdf`` suffix added by that method is stripped.

        Args:
            paper: The paper whose note stem is needed.

        Returns:
            A filesystem-safe string suitable for use as a note filename.
        """
        return paper.safe_filename(self._pattern).removesuffix(".pdf")

    def note_path(self, paper: Paper) -> Path:
        """Return the full path of the ``.md`` note for *paper*.

        Normally ``<note_stem>.md``.  When that file already holds the note of
        a *different* paper (two papers can slug to the same name), a
        uid-suffixed name is used instead so neither note is lost.

        Args:
            paper: Target paper.

        Returns:
            Absolute :class:`~pathlib.Path` to the note file (which may or
            may not exist yet).
        """
        return self._resolve_note_path(paper, {})

    def note_exists(self, paper: Paper) -> bool:
        """Return ``True`` if the expected note file already exists on disk.

        Args:
            paper: Paper to check.

        Returns:
            ``True`` when the note file is present; ``False`` otherwise.
        """
        return self.note_path(paper).exists()

    def export_papers(self, papers: list[Paper]) -> tuple[int, int]:
        """Write paper notes to the vault, skipping already-existing notes.

        Creates :attr:`notes_dir` if it does not exist.  For each paper whose
        note file is not yet present, renders and writes a new ``.md`` file.
        When :attr:`wikilinks` is enabled and the batch contains more than one
        paper, every note includes a *See also* section linking to the other
        papers in the batch.

        Args:
            papers: Papers to export.

        Returns:
            A ``(added, skipped)`` tuple — the number of notes written and the
            number skipped because the paper's note already existed.
        """
        self.notes_dir.mkdir(parents=True, exist_ok=True)

        # Resolve every note path up front — papers in the same batch may slug
        # to the same name — so wikilinks point at the files actually written.
        claimed: dict[Path, Paper] = {}
        paths: dict[int, Path] = {}
        for p in papers:
            path = self._resolve_note_path(p, claimed)
            paths[id(p)] = path
            claimed.setdefault(path, p)

        stems: dict[int, str] = (
            {id(p): paths[id(p)].stem for p in papers}
            if self._wikilinks and len(papers) > 1
            else {}
        )

        added = skipped = 0
        for paper in papers:
            path = paths[id(paper)]
            if path.exists():
                skipped += 1
                continue
            related = [stems[id(q)] for q in papers if q is not paper] if stems else []
            self._write_note(paper, related, path)
            added += 1
        return added, skipped

    # ── internals ─────────────────────────────────────────────────────────────

    def _resolve_note_path(self, paper: Paper, claimed: dict[Path, Paper]) -> Path:
        """Pick the note path for *paper*: the plain name unless another paper owns it.

        Args:
            paper: Target paper.
            claimed: Paths already assigned earlier in the current batch.
        """
        base = self.notes_dir / f"{self.note_stem(paper)}.md"
        suffix = hashlib.sha256(paper.uid.encode("utf-8")).hexdigest()[:6]
        alt = base.with_name(f"{base.stem}_{suffix}.md")
        for candidate in (base, alt):
            owner = claimed.get(candidate)
            if owner is not None:
                if owner.uid == paper.uid:
                    return candidate
                continue
            if not candidate.exists() or _note_is_for(candidate, paper):
                return candidate
        return alt

    def _write_note(self, paper: Paper, related_stems: list[str], path: Path) -> None:
        """Render *paper* and write the note file to disk.

        Args:
            paper: Paper to render.
            related_stems: Stems of other papers in the same batch, used to
                generate ``[[wikilinks]]`` in the *See also* section.
            path: Destination note file.
        """
        path.write_text(self._render(paper, related_stems), encoding="utf-8")

    def _render(self, paper: Paper, related_stems: list[str]) -> str:
        """Render a :class:`~mosaic.models.Paper` as an Obsidian Markdown string.

        Structure:

        1. YAML frontmatter (Obsidian *Properties*)
        2. H1 heading (paper title)
        3. Abstract callout (``> [!abstract]``) — omitted when no abstract
        4. Metadata table (field/value pairs)
        5. *See also* section with ``[[wikilinks]]`` — omitted when
           *related_stems* is empty

        Args:
            paper: The paper to render.
            related_stems: Filenames (without ``.md``) of other papers in the
                same export batch, used to generate ``[[wikilinks]]``.

        Returns:
            The complete Markdown string for the note, ending with a newline.
        """
        lines: list[str] = []

        # ── YAML frontmatter ─────────────────────────────────────────────────
        fm: dict = {"title": paper.title}
        if paper.authors:
            fm["authors"] = paper.authors
        if paper.year:
            fm["year"] = paper.year
        if paper.doi:
            fm["doi"] = paper.doi
        if paper.arxiv_id:
            fm["arxiv_id"] = paper.arxiv_id
        if paper.journal:
            fm["journal"] = paper.journal
        if paper.volume:
            fm["volume"] = paper.volume
        if paper.issue:
            fm["issue"] = paper.issue
        if paper.pages:
            fm["pages"] = paper.pages
        fm["source"] = paper.source
        fm["open_access"] = paper.is_open_access
        if paper.citation_count is not None:
            fm["citation_count"] = paper.citation_count
        if paper.pdf_url:
            fm["pdf_url"] = paper.pdf_url
        if paper.url:
            fm["url"] = paper.url
        fm["tags"] = self._tags

        lines.append(_frontmatter(fm))
        lines.append("")

        # ── H1 title ─────────────────────────────────────────────────────────
        lines.append(f"# {paper.title}")
        lines.append("")

        # ── Abstract callout ─────────────────────────────────────────────────
        if paper.abstract:
            lines.append("> [!abstract]")
            for part in paper.abstract.replace("\r\n", "\n").split("\n"):
                lines.append(f"> {part}".rstrip())
            lines.append("")

        # ── Metadata table ────────────────────────────────────────────────────
        rows: list[tuple[str, str]] = []
        if paper.authors:
            rows.append(("Authors", ", ".join(paper.authors)))
        if paper.year:
            rows.append(("Year", str(paper.year)))
        if paper.doi:
            rows.append(("DOI", paper.doi))
        if paper.arxiv_id:
            rows.append(("arXiv ID", paper.arxiv_id))
        if paper.journal:
            rows.append(("Journal", paper.journal))
        if paper.volume:
            rows.append(("Volume", paper.volume))
        if paper.issue:
            rows.append(("Issue", paper.issue))
        if paper.pages:
            rows.append(("Pages", paper.pages))
        rows.append(("Source", paper.source))
        if paper.is_open_access:
            rows.append(("Open Access", "yes"))
        if paper.citation_count is not None:
            rows.append(("Citations", str(paper.citation_count)))
        if paper.url:
            rows.append(("URL", f"[link]({paper.url})"))
        if paper.pdf_url:
            rows.append(("PDF", f"[link]({paper.pdf_url})"))

        lines.append("## Metadata")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        for field, value in rows:
            lines.append(f"| {field} | {value} |")
        lines.append("")

        # ── See also (wikilinks) ──────────────────────────────────────────────
        if related_stems:
            lines.append("## See also")
            lines.append("")
            for stem in related_stems:
                lines.append(f"- [[{stem}]]")
            lines.append("")

        return "\n".join(lines)
