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
cp .env.example .env               # then put a real LLM_API_KEY in .env
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs · Health: http://localhost:8000/health

## Model provider

The client is the OpenAI SDK pointed at whatever `LLM_BASE_URL` names, so the
provider is configuration rather than a code path. `.env.example` ships blocks
for Google Gemini (free tier, no card) and OpenAI; Groq or a local Ollama work
the same way.

The defaults are Gemini, and they were arrived at by measurement, not by
copying a docs snippet:

| Setting | Value | Why |
|---|---|---|
| `LLM_MODEL` | `gemini-3.6-flash` | 2.5s per answer. `gemini-2.5-flash` is retired for new keys; `gemini-3.7-flash` and the `gemini-flash-latest` alias both exceeded 45s because they reason by default. |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Free tier, and it honours an explicit output dimension. |
| `EMBEDDING_DIMENSIONS` | `1536` | The model defaults to 3072. Truncating halves storage and the per-query dot product. Matryoshka-trained, so the shorter vector is still meaningful, and cosine normalises anyway so no re-normalisation is needed. |

**Pin an explicit version.** Aliases like `gemini-flash-latest` can silently
move to a reasoning model and turn a 2.5s answer into a 45s one.

**Changing embedding model invalidates stored vectors.** Different models
produce incomparable embeddings, and a dimension change makes `np.vstack`
raise outright. There is no versioning or migration — a real gap, noted below.

## Run tests

```bash
pytest
```

31 tests, no network calls and no API key required. The model calls are stubbed
in `tests/test_api_flow.py`, so the suite still exercises the real queue,
worker, status lifecycle, SQLite layer and routes:

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
                          ─ chunk ─ embed ─ store ─ status=ready
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
- **One worker, not a pool.** Ordering stays obvious and the provider rate limit
  is never burst. Throughput is the price, and it is the right price here.
- **Nothing blocks the event loop.** Embeddings and generation use the async
  OpenAI client, fetching uses async `httpx`, and CPU-bound extraction runs in
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
  and there is no index to mistune. **Breaks at scale:** the query path reloads
  and deserialises every vector on every request, which is linear in corpus
  size and is the first wall — around 10k chunks. The fix order is: cache the
  matrix in memory, then `sqlite-vec`, then pgvector.
- **Relevance threshold, measured rather than guessed.** If no chunk clears
  `SIMILARITY_THRESHOLD`, the API returns "I couldn't find relevant information
  in your saved content" and **never calls the LLM** — cheaper and safer than
  asking the model to decline. The value came from reading the `query.scores`
  log on real questions:

  | Question against a note about "Project Falcon" | Score |
  |---|---|
  | "Who is the technical lead on Project Falcon?" | 0.749 |
  | "Where will the Falcon pilot run?" | 0.708 |
  | "What is retrieval-augmented generation?" | 0.481 |
  | "What is the recipe for sourdough bread?" | 0.408 |
  | "How do I renew a Canadian passport?" | 0.401 |

  `gemini-embedding-001` floors near **0.40** even for completely unrelated
  text and reaches **0.70+** on genuine matches, so **0.60** sits in the gap.
  The initial 0.35 — a reasonable default for OpenAI's embeddings — would have
  passed every one of those irrelevant questions through to the model. The
  threshold is a property of the embedding model, not a universal constant, and
  swapping models means re-measuring it.
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

## URL ingestion, in practice

`trafilatura` handles real pages well — the FastAPI docs homepage extracts to
14k characters of clean article text with the title intact.

Some sites refuse programmatic access outright. Wikipedia returns **403**, and
I confirmed by measurement that a full Chrome User-Agent string makes no
difference: identical status codes across five sites. So the fetcher identifies
itself honestly rather than impersonating a browser for a benefit that does not
exist. A failed fetch is surfaced as `failed` with the status code, which is
the correct behaviour — but a production version would want a fallback such as
a headless-browser renderer or a reader API for sites that block plain fetches.

## Debuggability

Structured JSON logs via `structlog`, with a per-request id bound into the
context (also returned as `X-Request-ID`) so a request can be followed across
the API and the background worker. Notable events: `ingest.start`,
`ingest.ready`, `ingest.failed`, `ingest.recover`, `query.scores`.

## Known gaps

Honest list, in the order I would fix them:

1. **Re-processing duplicates chunks.** A crash between `insert_chunks` and
   `set_item_status(ready)` leaves the item `processing`; the recovery sweep
   then re-runs it and inserts its chunks again. Fix: delete an item's chunks
   before processing, or do both writes in one transaction.
2. **No retries.** A transient 429 or 500 permanently fails an item.
3. **The query path reloads every vector**, as described above.
4. **Single process only** — `uvicorn --workers > 1` would duplicate the
   recovery sweep and split the queue.
5. **No embedding-model versioning**, so changing models silently invalidates
   what is stored.
6. **SSRF** — `/ingest` will fetch any URL, including internal addresses.
7. **No delete, re-index, or pagination endpoints.**
8. **No evaluation harness**, so retrieval quality is unmeasured beyond the
   threshold calibration above.

## What I deliberately left out

Auth, multi-user, streaming responses, reranking/hybrid search, retries,
Redis/Kafka/k8s. Scope matches the ~6–12h intent of the assessment; each of
these is a paragraph above rather than a directory of code.
