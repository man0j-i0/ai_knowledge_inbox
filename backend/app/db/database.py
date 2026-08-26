"""SQLite connection + schema. Sync driver — fine for single-user; at scale
you'd move to an async driver or run these in a thread pool (see README)."""
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id           TEXT PRIMARY KEY,
    type         TEXT NOT NULL CHECK (type IN ('note','url')),
    title        TEXT NOT NULL,
    source       TEXT,                      -- original URL for url items
    raw_content  TEXT,                      -- extracted/plain text
    status       TEXT NOT NULL DEFAULT 'processing'
                 CHECK (status IN ('processing','ready','failed')),
    error        TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id           TEXT PRIMARY KEY,
    item_id      TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    embedding    BLOB NOT NULL,             -- float32 vector, raw bytes
    token_count  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chunks_item ON chunks(item_id);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """One short-lived connection per unit of work, committed on success and
    always closed. `with sqlite3.connect(...)` alone commits but never closes,
    which leaks a file handle on every request.

    A connection per call (rather than a shared one) also sidesteps sqlite3's
    same-thread restriction, since the ingestion worker touches the DB from a
    different context than the request handlers.
    """
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
