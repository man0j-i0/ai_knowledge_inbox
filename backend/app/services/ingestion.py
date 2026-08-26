"""Asynchronous ingestion: an in-process asyncio.Queue drained by one worker.

Chosen deliberately over Redis/Celery because the assessment is single-user
and intentionally lightweight. The trade-off is durability: a crash loses
in-flight jobs and orphans items in 'processing'. We mitigate that on startup
with recover_orphaned_items(). In production this becomes a durable queue with
independently scalable workers (see README).

Single worker + single event loop keeps ordering simple and avoids bursting
the OpenAI rate limit.
"""
import asyncio
import uuid

from app.config import settings  # noqa: F401
from app.db import repository as repo
from app.lib import chunker, embeddings, url_fetcher
from app.logging_config import log
from app.schemas import ItemStatus, SourceType

# Built in start_worker(), not at import: an asyncio.Queue binds to the first
# event loop that touches it, so constructing it at import time ties the queue
# to whatever loop happened to import the module.
_queue: "asyncio.Queue[str] | None" = None
_worker_task: "asyncio.Task | None" = None


def _get_queue() -> "asyncio.Queue[str]":
    if _queue is None:
        raise RuntimeError("Ingestion worker is not running — call start_worker() first")
    return _queue


async def enqueue(item_id: str) -> None:
    await _get_queue().put(item_id)


async def _process_item(item_id: str) -> None:
    log.info("ingest.start", item_id=item_id)
    try:
        item = repo.get_item(item_id)
        if item is None:
            log.warn("ingest.missing_item", item_id=item_id)
            return

        if item["type"] == SourceType.url.value:
            # httpx (async) + trafilatura (via to_thread, inside the fetcher)
            title, content = await url_fetcher.fetch_and_extract(item["source"])
            repo.update_item_content(item_id, title, content)
        else:
            content = item["raw_content"] or ""

        chunk_texts = chunker.chunk_text(content)
        if not chunk_texts:
            raise ValueError("No content to index after chunking")

        vectors = await embeddings.embed_texts(chunk_texts)
        rows = [
            {
                "id": str(uuid.uuid4()),
                "item_id": item_id,
                "chunk_index": i,
                "content": text,
                "embedding": repo.embedding_to_blob(vec),
                "token_count": None,
            }
            for i, (text, vec) in enumerate(zip(chunk_texts, vectors))
        ]
        repo.insert_chunks(rows)
        repo.set_item_status(item_id, ItemStatus.ready)
        log.info("ingest.ready", item_id=item_id, chunks=len(rows))

    except Exception as exc:  # noqa: BLE001 — any failure must be recorded, not swallowed
        log.error("ingest.failed", item_id=item_id, error=str(exc))
        repo.set_item_status(item_id, ItemStatus.failed, error=str(exc))


async def _worker() -> None:
    log.info("worker.started")
    queue = _get_queue()
    while True:
        item_id = await queue.get()
        try:
            await _process_item(item_id)
        finally:
            queue.task_done()


async def recover_orphaned_items() -> None:
    """Re-enqueue items left 'processing' by a crash/restart. Without this an
    interrupted ingest is stuck forever — the honest cost of an in-process queue."""
    for item_id in repo.get_processing_item_ids():
        log.info("ingest.recover", item_id=item_id)
        await enqueue(item_id)


def start_worker() -> "asyncio.Task":
    global _queue, _worker_task
    _queue = asyncio.Queue()  # bind to the loop that is actually running
    _worker_task = asyncio.create_task(_worker())  # keep a ref so it isn't GC'd
    return _worker_task


async def stop_worker() -> None:
    """Cancel the worker on shutdown. Without this the pending task is simply
    dropped, which surfaces as 'Task was destroyed but it is pending'."""
    global _queue, _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
    _queue = None
    log.info("worker.stopped")
