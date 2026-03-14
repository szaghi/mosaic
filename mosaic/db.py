"""SQLite cache for papers and download status."""

from __future__ import annotations

import json
import logging
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
    """)
    con.commit()
    # Migrations — add columns introduced after the initial schema
    try:
        con.execute("ALTER TABLE papers ADD COLUMN citation_count INTEGER")
        con.commit()
    except sqlite3.OperationalError:
        log.debug("Migration: citation_count column already exists")


def upsert(con: sqlite3.Connection, paper: Paper) -> None:
    con.execute(
        """
        INSERT INTO papers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET
            pdf_url=excluded.pdf_url,
            abstract=excluded.abstract,
            is_open_access=excluded.is_open_access,
            citation_count=COALESCE(excluded.citation_count, papers.citation_count)
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
        self.con = _connect(db_path)
        self._lock = threading.RLock()

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
                """
                SELECT * FROM papers
                WHERE title LIKE ? OR abstract LIKE ?
            """,
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
