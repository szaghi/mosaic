"""SQLite cache for papers and download status."""
from __future__ import annotations
import sqlite3
import json
from pathlib import Path
from mosaic.models import Paper


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
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
            url          TEXT
        );
        CREATE TABLE IF NOT EXISTS downloads (
            uid        TEXT PRIMARY KEY,
            local_path TEXT,
            status     TEXT,
            downloaded_at TEXT DEFAULT (datetime('now'))
        );
    """)
    con.commit()


def upsert(con: sqlite3.Connection, paper: Paper) -> None:
    con.execute("""
        INSERT INTO papers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET
            pdf_url=excluded.pdf_url,
            abstract=excluded.abstract,
            is_open_access=excluded.is_open_access
    """, (
        paper.uid, paper.title,
        json.dumps(paper.authors), paper.year,
        paper.doi, paper.arxiv_id, paper.pii,
        paper.abstract, paper.journal,
        paper.volume, paper.issue, paper.pages,
        paper.pdf_url, paper.source,
        int(paper.is_open_access), paper.url,
    ))
    con.commit()


def set_download(con: sqlite3.Connection, uid: str, local_path: str, status: str) -> None:
    con.execute("""
        INSERT INTO downloads(uid, local_path, status)
        VALUES (?,?,?)
        ON CONFLICT(uid) DO UPDATE SET local_path=excluded.local_path, status=excluded.status
    """, (uid, local_path, status))
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
    )


class Cache:
    def __init__(self, db_path: str):
        self.con = _connect(db_path)

    def save(self, paper: Paper) -> None:
        upsert(self.con, paper)

    def set_download(self, uid: str, local_path: str, status: str) -> None:
        set_download(self.con, uid, local_path, status)

    def get_download(self, uid: str) -> sqlite3.Row | None:
        return get_download(self.con, uid)

    def search_local(self, query: str) -> list[Paper]:
        rows = self.con.execute("""
            SELECT * FROM papers
            WHERE title LIKE ? OR abstract LIKE ?
        """, (f"%{query}%", f"%{query}%")).fetchall()
        return [row_to_paper(r) for r in rows]
