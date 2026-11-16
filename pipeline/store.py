"""SQLite store for works, passages, links, evidence, reviews, articles and signature terms."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    year INTEGER,
    year_approximate INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,          -- gutenberg-us, gutenberg-au, local-file, stub
    source_ref TEXT,               -- ebook ID, URL or file path
    kind TEXT NOT NULL,            -- full, stub, subwork
    parent_id INTEGER REFERENCES works(id),
    start_pos INTEGER,             -- subwork only: character range in the parent's stripped text
    end_pos INTEGER,
    translated INTEGER NOT NULL DEFAULT 0,
    text_year INTEGER              -- when the held text was written, if later than `year` (a translation)
);
CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL REFERENCES works(id),
    seq INTEGER NOT NULL,
    position INTEGER NOT NULL,     -- character offset of the passage in the work's stripped text
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS passages_work ON passages(work_id, seq);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    citation TEXT NOT NULL,
    location TEXT NOT NULL UNIQUE, -- URL or file path
    added TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES works(id),   -- the later work, which draws on the target
    target_id INTEGER NOT NULL REFERENCES works(id),
    type TEXT NOT NULL,
    detector TEXT NOT NULL,
    detector_version TEXT NOT NULL,
    score REAL NOT NULL,           -- the detector's raw score, 0 to 1
    rationale TEXT NOT NULL DEFAULT '',
    evidence_key TEXT NOT NULL,    -- identifies this evidence for the judgement cache
    article_id INTEGER REFERENCES articles(id),
    UNIQUE (source_id, target_id, type)
);
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY,
    link_id INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    source_passage_id INTEGER REFERENCES passages(id),
    target_passage_id INTEGER REFERENCES passages(id),
    source_quote TEXT,
    target_quote TEXT
);
CREATE TABLE IF NOT EXISTS judgements (
    evidence_key TEXT PRIMARY KEY,
    verdict TEXT NOT NULL,         -- accept, reject
    confidence REAL NOT NULL,
    rationale TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'haiku'  -- the model that gave the verdict; before this was kept, always haiku
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES works(id),
    target_id INTEGER NOT NULL REFERENCES works(id),
    type TEXT NOT NULL,            -- the type the link was detected as
    verdict TEXT NOT NULL,         -- accept, reject
    corrected_type TEXT,
    note TEXT,
    created TEXT NOT NULL,
    UNIQUE (source_id, target_id, type)
);
CREATE TABLE IF NOT EXISTS signature_terms (
    id INTEGER PRIMARY KEY,
    term TEXT NOT NULL,
    work_id INTEGER NOT NULL REFERENCES works(id),
    weight REAL NOT NULL,
    article_id INTEGER REFERENCES articles(id),
    review_id INTEGER REFERENCES reviews(id),
    UNIQUE (term, work_id)
);
CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL REFERENCES works(id),
    theme TEXT NOT NULL,           -- a short label, as the model wrote it for this work
    canonical TEXT,                -- the label it was merged into, if another wording of the same theme
    note TEXT NOT NULL DEFAULT '', -- one sentence on how this work treats the theme
    model TEXT NOT NULL,           -- the command that produced the label
    UNIQUE (work_id, theme)
);
"""


class Store:
    """One data directory: ``book_links.db`` plus cached texts under ``texts/``."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.data_dir / "book_links.db", timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        if "model" not in {row["name"] for row in self.conn.execute("PRAGMA table_info(judgements)")}:
            self.conn.execute("ALTER TABLE judgements ADD COLUMN model TEXT NOT NULL DEFAULT 'haiku'")
            self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        self.conn.close()

    # works -----------------------------------------------------------------

    def find_work(self, title, author=None):
        """The work with this title (and author, if given), or None."""
        if author is None:
            row = self.conn.execute("SELECT * FROM works WHERE title = ?", (title,)).fetchone()
        else:
            row = self.conn.execute("SELECT * FROM works WHERE title = ? AND author = ?", (title, author)).fetchone()
        return row

    def add_work(
        self,
        title,
        author,
        year,
        source,
        kind,
        source_ref=None,
        parent_id=None,
        start_pos=None,
        end_pos=None,
        text_year=None,
    ):
        """Insert a work and return its id. A work with the same title and author is reused.

        ``text_year`` is the year a translation was made; giving it marks the work as translated.
        """
        existing = self.find_work(title, author)
        if existing is not None:
            return existing["id"]
        cursor = self.conn.execute(
            "INSERT INTO works (title, author, year, source, source_ref, kind, parent_id, start_pos, end_pos, translated, text_year)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                author,
                year,
                source,
                source_ref,
                kind,
                parent_id,
                start_pos,
                end_pos,
                int(text_year is not None),
                text_year,
            ),
        )
        return cursor.lastrowid

    def works(self):
        return self.conn.execute("SELECT * FROM works ORDER BY id").fetchall()

    def work(self, work_id):
        return self.conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()

    # passages --------------------------------------------------------------

    def set_passages(self, work_id, passages):
        """Replace a work's passages. ``passages`` is an iterable of (position, text).

        Evidence quoting the old passages is removed; the next ``detect`` rebuilds it.
        """
        old = "SELECT id FROM passages WHERE work_id = ?"
        self.conn.execute(
            f"DELETE FROM evidence WHERE source_passage_id IN ({old}) OR target_passage_id IN ({old})",
            (work_id, work_id),
        )
        self.conn.execute("DELETE FROM passages WHERE work_id = ?", (work_id,))
        self.conn.executemany(
            "INSERT INTO passages (work_id, seq, position, text) VALUES (?, ?, ?, ?)",
            [(work_id, seq, position, text) for seq, (position, text) in enumerate(passages)],
        )

    def passages(self, work_id):
        return self.conn.execute("SELECT * FROM passages WHERE work_id = ? ORDER BY seq", (work_id,)).fetchall()

    def has_passages(self, work_id):
        return self.conn.execute("SELECT 1 FROM passages WHERE work_id = ? LIMIT 1", (work_id,)).fetchone() is not None
