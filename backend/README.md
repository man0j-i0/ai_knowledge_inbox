# AI Knowledge Inbox — Backend

FastAPI service that ingests notes and URLs, indexes them for semantic search,
and answers questions over the saved content with cited sources.

> **TODO before submitting:** rewrite the "Design decisions & tradeoffs"
> section below in your own voice — it is the graded part, and it should read
> like you made these calls, because you did. Then delete this note.

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # then put your real OPENAI_API_KEY in .env
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs · Health: http://localhost:8000/health

## Run tests

```bash
pytest
```

31 tests, no network calls and no API key required. The OpenAI calls are
stubbed in `tests/test_api_flow.py`, so the suite still exercises the real
queue, worker, status lifecycle, SQLite layer and routes:

- `test_chunker.py` — boundary behaviour, overlap, size ceiling, degenerate input
- `test_similarity.py` — cosine correctness, ranking order, no input mutation
- `test_api_flow.py` — ingest → worker → ready → query end to end, plus the
  failure paths: a URL that 404s, an empty inbox, a question nothing matches,
  and every invalid payload shape

## Endpoints

| Method | Path      | Purpose                                              |
|--------|-----------|------------------------------------------------------|
| POST   | `/ingest` | Add a note or URL. Returns **202** + item id/status.  |
| GET    | `/items`  | List saved items with `status` and `chunk_count`.     |
| POST   | `/query`  | Ask a question. Returns an answer + cited sources.    |

`/ingest` answers **202 Accepted**, not 201: the item exists but is not yet
searchable. Clients poll `/items` for `processing → ready | failed`.
Invalid payloads return **422** with the offending field, via Pydantic.

## Architecture

```
React ──REST──> FastAPI ──> SQLite (items, chunks+embeddings)
                   │
                   ├── POST /ingest ──> create item (status=processing)
                   │                    └─ enqueue(item_id) ──> 202
                   │
                   └── asyncio.Queue ──> ingestion worker
                          fetch (httpx) ─ extract (trafilatura, to_thread)
                          ─ chunk ─ embed (AsyncOpenAI) ─ store ─ status=ready
                                                          └─ on error ─ status=failed
query: embed question ─ cosine top-k ─ threshold ─ prompt ─ LLM ─ answer+sources
```

Layering is strict: `api/` handles HTTP only, `services/` orchestrates,
`lib/` holds pure/single-purpose helpers, `db/repository.py` owns every line of
SQL. No module reaches past its neighbour.

## Design decisions & tradeoffs

- **Asynchronous ingestion via an in-process `asyncio.Queue`.** `/ingest`
  returns `202` immediately; a single background worker fetches, extracts,
  chunks, embeds, and flips the item `processing → ready` (or `failed`). Chosen
  over Redis/Celery because the assessment is single-user and deliberately
  lightweight. **Tradeoff:** no durability — a crash orphans in-flight items,
  so `recover_orphaned_items()` re-enqueues anything left `processing` at
  startup. In production this becomes a durable queue (SQS/Redis) with
  independently scalable workers and a retry/dead-letter policy.
- **One worker, not a pool.** Ordering stays obvious and the OpenAI rate limit
  is never burst. Throughput is the price, and it is the right price here.
- **Nothing blocks the event loop.** Embeddings and generation use
  `AsyncOpenAI`, fetching uses async `httpx`, and CPU-bound extraction runs in
  `asyncio.to_thread`. A slow ingest never freezes the API — which is the
  whole point of doing this asynchronously in the first place.
- **Three states, not two.** `failed` carries the reason ("returned HTTP 404",
  "no readable article content") all the way to the UI. Without it a broken
  URL just spins on `processing` forever and the user has no idea why.
- **Chunking:** recursive and boundary-aware, ~600 tokens with ~80 overlap,
  descending paragraph → sentence → hard token cut only as far as needed.
  Small chunks lose the context that makes them findable; large ones average a
  specific fact into a vague topic vector and waste prompt budget. Overlap
  keeps a fact that straddles a boundary intact in at least one chunk. A short
  note stays one chunk.
- **Vector store:** embeddings as float32 BLOBs in SQLite, brute-force NumPy
  cosine at query time. Sub-millisecond at this scale, exactly reproducible,
  and there is no index to mistune. **Breaks at scale:** O(n·d) per query with
  every vector resident in memory. Past roughly 10k–100k chunks, move to an ANN
  index — `sqlite-vec` to stay in-process, or pgvector/Qdrant to move out.
- **Relevance threshold:** if no chunk clears `SIMILARITY_THRESHOLD`, the API
  returns a plain "I couldn't find that in your saved content" instead of
  letting the model improvise. The value is tuned by reading the `query.scores`
  log line on real questions — not copied from a blog post.
- **Citations:** retrieved chunks are numbered `[n]` in the prompt and mapped
  back to source items in the response, so every claim is traceable.
- **A connection per unit of work.** `get_connection()` is a context manager
  that commits on success, rolls back on failure, and always closes.
  `with sqlite3.connect(...)` alone commits but never closes, which leaks a
  handle per request; a fresh connection also sidesteps sqlite3's same-thread
  restriction, since the worker touches the DB from a different context than
  the request handlers.
- **No LangChain.** Chunk / embed / retrieve / prompt is a few readable
  functions. Every step is explainable and debuggable, and there is no
  framework abstraction between me and a bad retrieval result.

## Debuggability

Structured JSON logs via `structlog`, with a per-request id bound into the
context (also returned as `X-Request-ID`) so a request can be followed across
the API and the background worker. Notable events: `ingest.start`,
`ingest.ready`, `ingest.failed`, `ingest.recover`, `query.scores`.

## What I deliberately left out

Auth, multi-user, streaming responses, reranking/hybrid search, retries,
Redis/Kafka/k8s. Scope matches the ~6–12h intent of the assessment; each of
these is a paragraph above rather than a directory of code.
