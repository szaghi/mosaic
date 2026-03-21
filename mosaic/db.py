"""SQLite cache for papers and download status."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path

from mosaic.models import Paper

log = logging.getLogger(__name__)


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    _init(con)
    return con


def _init(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            uid          TEXT PRIMARY KEY,
            title        TEXT NOT NULL,
            authors      TEXT,
            year         INTEGER,
            doi          TEXT,
            arxiv_id     TEXT,
            pii          TEXT,
            abstract     TEXT,
            journal      TEXT,
            volume       TEXT,
            issue        TEXT,
            pages        TEXT,
            pdf_url      TEXT,
            source       TEXT,
            is_open_access INTEGER DEFAULT 0,
            url          TEXT,
            citation_count INTEGER
        );
        CREATE TABLE IF NOT EXISTS downloads (
            uid        TEXT PRIMARY KEY,
            local_path TEXT,
            status     TEXT,
            downloaded_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS searches (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            query        TEXT NOT NULL,
            filters_json TEXT,
            sources_json TEXT,
            created_at   TEXT DEFAULT (datetime('now')),
            result_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS exports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid         TEXT NOT NULL,
            format      TEXT NOT NULL,
            destination TEXT DEFAULT '',
            exported_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS exports_uid_fmt ON exports(uid, format, destination);
    """)
    con.commit()
    # Migrations — add columns introduced after the initial schema
    for stmt in (
        "ALTER TABLE papers ADD COLUMN citation_count INTEGER",
    ):
        try:
            con.execute(stmt)
            con.commit()
        except sqlite3.OperationalError:
            pass  # column already exists


def upsert(con: sqlite3.Connection, paper: Paper) -> None:
    """Insert *paper* or enrich the existing row with field-level merge rules.

    Rules (applied only on conflict):
    - abstract       : keep the longer version
    - pdf_url        : preserve the existing value (never overwrite with a new one)
    - is_open_access : True supersedes False (OR / MAX)
    - citation_count : keep the higher value; NULL is treated as "unknown"
    - authors        : keep the longer JSON array
    - doi/arxiv_id/pii, journal, volume, issue, pages, url : fill if empty
    - title, year, source : keep the first-recorded value
    """
    con.execute(
        """
        INSERT INTO papers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET
            abstract = CASE
                WHEN excluded.abstract IS NULL THEN papers.abstract
                WHEN papers.abstract IS NULL   THEN excluded.abstract
                WHEN length(excluded.abstract) > length(papers.abstract) THEN excluded.abstract
                ELSE papers.abstract
            END,
            pdf_url = COALESCE(papers.pdf_url, excluded.pdf_url),
            is_open_access = MAX(papers.is_open_access, excluded.is_open_access),
            citation_count = CASE
                WHEN excluded.citation_count IS NULL THEN papers.citation_count
                WHEN papers.citation_count IS NULL   THEN excluded.citation_count
                ELSE MAX(papers.citation_count, excluded.citation_count)
            END,
            authors = CASE
                WHEN json_array_length(excluded.authors) > json_array_length(COALESCE(papers.authors, '[]'))
                    THEN excluded.authors
                ELSE papers.authors
            END,
            doi      = COALESCE(papers.doi,      excluded.doi),
            arxiv_id = COALESCE(papers.arxiv_id, excluded.arxiv_id),
            pii      = COALESCE(papers.pii,      excluded.pii),
            journal  = COALESCE(papers.journal,  excluded.journal),
            volume   = COALESCE(papers.volume,   excluded.volume),
            issue    = COALESCE(papers.issue,    excluded.issue),
            pages    = COALESCE(papers.pages,    excluded.pages),
            url      = COALESCE(papers.url,      excluded.url)
        """,
        (
            paper.uid,
            paper.title,
            json.dumps(paper.authors),
            paper.year,
            paper.doi,
            paper.arxiv_id,
            paper.pii,
            paper.abstract,
            paper.journal,
            paper.volume,
            paper.issue,
            paper.pages,
            paper.pdf_url,
            paper.source,
            int(paper.is_open_access),
            paper.url,
            paper.citation_count,
        ),
    )
    con.commit()


def set_download(con: sqlite3.Connection, uid: str, local_path: str, status: str) -> None:
    con.execute(
        """
        INSERT INTO downloads(uid, local_path, status)
        VALUES (?,?,?)
        ON CONFLICT(uid) DO UPDATE SET local_path=excluded.local_path, status=excluded.status
    """,
        (uid, local_path, status),
    )
    con.commit()


def get_download(con: sqlite3.Connection, uid: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM downloads WHERE uid=?", (uid,)).fetchone()


def row_to_paper(row: sqlite3.Row) -> Paper:
    return Paper(
        title=row["title"],
        authors=json.loads(row["authors"] or "[]"),
        year=row["year"],
        doi=row["doi"],
        arxiv_id=row["arxiv_id"],
        pii=row["pii"],
        abstract=row["abstract"],
        journal=row["journal"],
        volume=row["volume"],
        issue=row["issue"],
        pages=row["pages"],
        pdf_url=row["pdf_url"],
        source=row["source"],
        is_open_access=bool(row["is_open_access"]),
        url=row["url"],
        citation_count=row["citation_count"],
    )


class Cache:
    """Thread-safe SQLite cache.

    All public methods are protected by a reentrant lock so that the cache
    can be shared safely across ``ThreadPoolExecutor`` workers.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self.con = _connect(db_path)
        self._lock = threading.RLock()

    # ── Basic read/write ──────────────────────────────────────────────────────

    def save(self, paper: Paper) -> None:
        with self._lock:
            upsert(self.con, paper)

    def set_download(self, uid: str, local_path: str, status: str) -> None:
        with self._lock:
            set_download(self.con, uid, local_path, status)

    def get_download(self, uid: str) -> sqlite3.Row | None:
        with self._lock:
            return get_download(self.con, uid)

    def get_by_uid(self, uid: str) -> Paper | None:
        with self._lock:
            row = self.con.execute("SELECT * FROM papers WHERE uid=?", (uid,)).fetchone()
            return row_to_paper(row) if row else None

    def search_local(self, query: str) -> list[Paper]:
        with self._lock:
            rows = self.con.execute(
                "SELECT * FROM papers WHERE title LIKE ? OR abstract LIKE ?",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
            return [row_to_paper(r) for r in rows]

    def save_search(
        self, query: str, filters_json: str = "", sources_json: str = "", result_count: int = 0
    ) -> None:
        with self._lock:
            self.con.execute(
                "INSERT INTO searches(query, filters_json, sources_json, result_count) VALUES (?,?,?,?)",
                (query, filters_json, sources_json, result_count),
            )
            self.con.commit()

    def list_searches(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self.con.execute(
                "SELECT * FROM searches ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Richness predicate (Phase 5) ──────────────────────────────────────────

    def is_rich(self, uid: str) -> bool:
        """True when the cached record has abstract, year, and at least one author."""
        with self._lock:
            row = self.con.execute(
                "SELECT abstract, year, authors FROM papers WHERE uid=?", (uid,)
            ).fetchone()
            if not row:
                return False
            authors = json.loads(row["authors"] or "[]")
            return bool(row["abstract"] and row["year"] and authors)

    def rich_uids(self) -> set[str]:
        """Return the set of UIDs whose records are considered rich (abstract + year + authors)."""
        with self._lock:
            rows = self.con.execute(
                "SELECT uid, abstract, year, authors FROM papers "
                "WHERE abstract IS NOT NULL AND year IS NOT NULL"
            ).fetchall()
            result: set[str] = set()
            for row in rows:
                if json.loads(row["authors"] or "[]"):
                    result.add(row["uid"])
            return result

    # ── Cache management (Phase 4) ────────────────────────────────────────────

    def stats(self) -> dict:
        """Return a summary dict of cache contents."""
        with self._lock:
            papers         = self.con.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
            downloaded     = self.con.execute(
                "SELECT COUNT(*) FROM downloads WHERE status='ok'"
            ).fetchone()[0]
            searches       = self.con.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
            with_abstract  = self.con.execute(
                "SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL"
            ).fetchone()[0]
            with_pdf_url   = self.con.execute(
                "SELECT COUNT(*) FROM papers WHERE pdf_url IS NOT NULL"
            ).fetchone()[0]
            open_access    = self.con.execute(
                "SELECT COUNT(*) FROM papers WHERE is_open_access=1"
            ).fetchone()[0]
            exports_total  = self.con.execute("SELECT COUNT(*) FROM exports").fetchone()[0]

        try:
            db_bytes = os.path.getsize(self._db_path)
        except OSError:
            db_bytes = 0

        return {
            "papers": papers,
            "downloaded": downloaded,
            "searches": searches,
            "with_abstract": with_abstract,
            "with_pdf_url": with_pdf_url,
            "open_access": open_access,
            "exports": exports_total,
            "db_bytes": db_bytes,
        }

    def list_papers(
        self, limit: int = 50, offset: int = 0, query: str = ""
    ) -> list[Paper]:
        """Return cached papers, newest-first, with optional substring filter."""
        with self._lock:
            if query:
                rows = self.con.execute(
                    "SELECT * FROM papers WHERE title LIKE ? OR abstract LIKE ? "
                    "ORDER BY rowid DESC LIMIT ? OFFSET ?",
                    (f"%{query}%", f"%{query}%", limit, offset),
                ).fetchall()
            else:
                rows = self.con.execute(
                    "SELECT * FROM papers ORDER BY rowid DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [row_to_paper(r) for r in rows]

    def count_papers(self, query: str = "") -> int:
        """Total number of papers matching *query* (or all papers if empty)."""
        with self._lock:
            if query:
                return self.con.execute(
                    "SELECT COUNT(*) FROM papers WHERE title LIKE ? OR abstract LIKE ?",
                    (f"%{query}%", f"%{query}%"),
                ).fetchone()[0]
            return self.con.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    def verify_downloads(self) -> list[dict]:
        """Check whether each tracked download file still exists on disk.

        Returns a list of dicts with keys ``uid``, ``local_path``, ``exists``.
        """
        with self._lock:
            rows = self.con.execute(
                "SELECT uid, local_path FROM downloads WHERE status='ok'"
            ).fetchall()
        return [
            {"uid": row["uid"], "local_path": row["local_path"],
             "exists": bool(row["local_path"] and Path(row["local_path"]).exists())}
            for row in rows
        ]

    def clean_stubs(self) -> int:
        """Remove download records whose files no longer exist on disk.

        Returns the number of records removed.
        """
        with self._lock:
            rows = self.con.execute(
                "SELECT uid, local_path FROM downloads WHERE status='ok'"
            ).fetchall()
            removed = 0
            for row in rows:
                if not row["local_path"] or not Path(row["local_path"]).exists():
                    self.con.execute("DELETE FROM downloads WHERE uid=?", (row["uid"],))
                    removed += 1
            if removed:
                self.con.commit()
            return removed

    def clear(self) -> None:
        """Wipe all papers, downloads, searches, and exports from the cache."""
        with self._lock:
            self.con.executescript(
                "DELETE FROM papers; DELETE FROM downloads; "
                "DELETE FROM searches; DELETE FROM exports;"
            )
            self.con.commit()

    # ── Export tracking (Phase 4) ─────────────────────────────────────────────

    def track_export(self, uid: str, fmt: str, destination: str = "") -> None:
        """Record that *uid* was exported in format *fmt* to *destination*."""
        with self._lock:
            self.con.execute(
                "INSERT INTO exports(uid, format, destination) VALUES (?,?,?)",
                (uid, fmt, destination),
            )
            self.con.commit()

    def was_exported(self, uid: str, fmt: str, destination: str = "") -> bool:
        """True if *uid* was previously exported in *fmt* to *destination*."""
        with self._lock:
            return self.con.execute(
                "SELECT 1 FROM exports WHERE uid=? AND format=? AND destination=?",
                (uid, fmt, destination),
            ).fetchone() is not None
