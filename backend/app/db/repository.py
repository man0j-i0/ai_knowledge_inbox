"""All SQL lives here. Services never touch the DB directly."""
from datetime import datetime, timezone

import numpy as np

from app.db.database import get_connection
from app.schemas import ItemStatus, SourceType


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def embedding_to_blob(vec) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def create_item(item_id: str, type_: SourceType, title: str,
                source: str | None, raw_content: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO items (id, type, title, source, raw_content, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, type_.value, title, source, raw_content,
             ItemStatus.processing.value, _now_iso()),
        )


def get_item(item_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None


def update_item_content(item_id: str, title: str, raw_content: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE items SET title = ?, raw_content = ? WHERE id = ?",
                     (title, raw_content, item_id))


def set_item_status(item_id: str, status: ItemStatus, error: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE items SET status = ?, error = ? WHERE id = ?",
                     (status.value, error, item_id))


def replace_chunks_and_mark_ready(item_id: str, chunks: list[dict]) -> None:
    """Swap in an item's chunks and mark it ready — atomically.

    Ingestion is replayable: recover_orphaned_items() re-enqueues anything left
    'processing' by a crash. Inserting without clearing first would mean a crash
    between the insert and the status flip leaves chunks behind, and the replay
    appends a *second* copy — so the same passage could be retrieved and cited
    twice. Deleting first makes processing idempotent, and doing all three
    statements in one transaction means a crash can never leave an item marked
    ready against a half-written set of chunks.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM chunks WHERE item_id = ?", (item_id,))
        conn.executemany(
            "INSERT INTO chunks (id, item_id, chunk_index, content, embedding, token_count)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(c["id"], c["item_id"], c["chunk_index"], c["content"],
              c["embedding"], c.get("token_count")) for c in chunks],
        )
        conn.execute(
            "UPDATE items SET status = ?, error = NULL WHERE id = ?",
            (ItemStatus.ready.value, item_id),
        )


def delete_item(item_id: str) -> bool:
    """Remove an item. Returns False if there was nothing to remove, so the
    route can answer 404 rather than pretending it deleted something.

    Chunks go with it via ON DELETE CASCADE — which only fires because
    get_connection() sets PRAGMA foreign_keys = ON. SQLite ignores foreign keys
    by default, so without that pragma this would silently orphan every chunk.
    """
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        return cursor.rowcount > 0


def list_items() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT i.*, COUNT(c.id) AS chunk_count"
            " FROM items i LEFT JOIN chunks c ON c.item_id = i.id"
            " GROUP BY i.id ORDER BY i.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_ready_chunks() -> list[dict]:
    """All chunks belonging to items that finished ingesting."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT c.id, c.item_id, c.content, c.embedding,"
            "       i.title, i.source"
            " FROM chunks c JOIN items i ON i.id = c.item_id"
            " WHERE i.status = 'ready'"
        ).fetchall()
        return [dict(r) for r in rows]


def get_processing_item_ids() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM items WHERE status = 'processing'").fetchall()
        return [r["id"] for r in rows]
