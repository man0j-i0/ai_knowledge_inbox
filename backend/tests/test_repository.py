"""Tests for db/repository.py — specifically that ingestion is replayable.

The startup recovery sweep re-enqueues items left 'processing' by a crash, so
processing an item twice is a normal path, not an edge case. If it were not
idempotent, a crash would quietly double an item's chunks and the same passage
could be retrieved and cited twice.
"""
import uuid

import numpy as np
import pytest

from app.config import settings
from app.db import repository as repo
from app.db.database import init_db
from app.schemas import ItemStatus, SourceType


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "repo_test.db"))
    init_db()
    return tmp_path


def _chunks(item_id: str, count: int) -> list[dict]:
    return [
        {
            "id": str(uuid.uuid4()),
            "item_id": item_id,
            "chunk_index": index,
            "content": f"chunk {index}",
            "embedding": repo.embedding_to_blob(np.array([1.0, 0.0], dtype=np.float32)),
            "token_count": 3,
        }
        for index in range(count)
    ]


def _make_item(db) -> str:
    item_id = str(uuid.uuid4())
    repo.create_item(item_id, SourceType.note, "t", None, "body")
    return item_id


def test_reprocessing_does_not_duplicate_chunks(db):
    item_id = _make_item(db)

    repo.replace_chunks_and_mark_ready(item_id, _chunks(item_id, 3))
    repo.replace_chunks_and_mark_ready(item_id, _chunks(item_id, 3))

    stored = [c for c in repo.get_ready_chunks() if c["item_id"] == item_id]
    assert len(stored) == 3, "replaying ingestion must not append a second copy"


def test_reprocessing_reflects_the_new_chunking(db):
    item_id = _make_item(db)

    repo.replace_chunks_and_mark_ready(item_id, _chunks(item_id, 5))
    repo.replace_chunks_and_mark_ready(item_id, _chunks(item_id, 2))

    stored = [c for c in repo.get_ready_chunks() if c["item_id"] == item_id]
    assert len(stored) == 2, "re-indexing should replace, not merge"


def test_marking_ready_clears_a_previous_error(db):
    item_id = _make_item(db)
    repo.set_item_status(item_id, ItemStatus.failed, error="temporary failure")

    repo.replace_chunks_and_mark_ready(item_id, _chunks(item_id, 1))

    item = repo.get_item(item_id)
    assert item["status"] == ItemStatus.ready.value
    assert item["error"] is None, "a successful retry must clear the old error"


def test_only_ready_items_are_searchable(db):
    ready_id = _make_item(db)
    pending_id = _make_item(db)

    repo.replace_chunks_and_mark_ready(ready_id, _chunks(ready_id, 2))
    # pending_id keeps its default 'processing' status

    item_ids = {c["item_id"] for c in repo.get_ready_chunks()}
    assert ready_id in item_ids
    assert pending_id not in item_ids


def test_orphan_sweep_finds_only_processing_items(db):
    ready_id = _make_item(db)
    stuck_id = _make_item(db)
    repo.replace_chunks_and_mark_ready(ready_id, _chunks(ready_id, 1))

    orphans = repo.get_processing_item_ids()

    assert stuck_id in orphans
    assert ready_id not in orphans
