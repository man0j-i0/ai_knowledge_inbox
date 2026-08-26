# AI Knowledge Inbox

Save notes and links, then ask questions across everything you saved and get an
answer with citations back to the source.

A FastAPI backend handles ingestion and retrieval-augmented answering; a React
frontend adds items, shows what has been indexed, and asks questions.

> **TODO before submitting:** the tradeoffs sections here and in
> [`backend/README.md`](backend/README.md) are the graded part — rewrite them
> in your own voice, add a screenshot or short GIF below, then delete this note.

## Quick start

Two terminals. Backend first.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # add your real OPENAI_API_KEY
uvicorn app.main:app --reload      # http://localhost:8000
```

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

Interactive API docs: http://localhost:8000/docs

The backend whitelists `http://localhost:5173` for CORS. If you change the Vite
port, change `allow_origins` in `backend/app/main.py` to match.

## How it works

```
                    ┌──────────────────────────────────────────┐
  React (hooks)     │  FastAPI                                 │
   add note/URL ──► │   POST /ingest ──► create item, enqueue  │──► 202
   items + status ◄─│   GET  /items  ──► list + status         │
   ask question ──► │   POST /query  ──► RAG pipeline          │
   answer+sources ◄─│                                          │
                    └───────┬──────────────────────┬───────────┘
                            │                      │
         ┌──────────────────▼─────┐   ┌────────────▼─────────────┐
         │ ingestion worker       │   │ query pipeline           │
         │ (asyncio.Queue)        │   │ embed question           │
         │  fetch  (httpx)        │   │ cosine over all chunks   │
         │  extract (trafilatura) │   │ threshold + top-k        │
         │  chunk                 │   │ numbered context → LLM   │
         │  embed  (AsyncOpenAI)  │   │ answer + cited sources   │
         │  → ready | failed      │   └────────────┬─────────────┘
         └──────────────────┬─────┘                │
                     ┌──────▼────────────────────────────┐
                     │ SQLite: items, chunks + embeddings │
                     └────────────────────────────────────┘
```

Ingestion is **asynchronous**. `POST /ingest` records the item and returns
`202 Accepted` immediately; a background worker does the slow work and moves
the item `processing → ready`, or `failed` with the reason attached. The
frontend polls `/items` while anything is still processing and stops once the
inbox is idle.

## API

| Method | Path      | Purpose                                                    |
|--------|-----------|------------------------------------------------------------|
| POST   | `/ingest` | Add a note or URL. **202** with the new item id and status. |
| GET    | `/items`  | List saved items with `status`, `chunk_count`, and `error`. |
| POST   | `/query`  | Ask a question. Returns an answer plus cited sources.       |
| GET    | `/health` | Liveness check.                                             |

Invalid payloads return **422** naming the offending field. Every response
carries an `X-Request-ID` that also appears in the structured logs, so a single
request can be followed across the API and the background worker.

## Layout

```
backend/
  app/
    api/        HTTP only — parse, delegate, return
    services/   orchestration: ingestion pipeline, RAG pipeline
    lib/        single-purpose helpers: chunker, similarity, fetcher, clients
    db/         schema + every line of SQL
  tests/        unit tests and a stubbed end-to-end flow test
frontend/
  src/
    api/        the only module that touches the network
    hooks/      useItems (with polling), useIngest, useAsk
    components/ form, item list, ask panel, answer + sources
```

## Tests

```bash
cd backend && pytest        # 31 tests, no network and no API key needed
cd frontend && npm run build   # typecheck + production build
```

The backend suite stubs the two OpenAI calls with deterministic vectors and
drives the real queue, worker, database and routes end to end — including a URL
that 404s, an empty inbox, a question nothing matches, and every invalid
payload shape.

## Design decisions

Written up in full in [`backend/README.md`](backend/README.md). The short
version:

- **Async ingestion via an in-process `asyncio.Queue`** rather than Celery or
  Redis, because this is single-user by design. The cost is durability, so
  items left `processing` by a crash are re-enqueued at startup.
- **Nothing blocks the event loop** — async OpenAI and httpx clients, with
  CPU-bound content extraction pushed to a worker thread.
- **Three item states, not two.** `failed` carries the reason to the UI, so a
  broken URL explains itself instead of spinning forever.
- **Chunking** is recursive and boundary-aware, ~600 tokens with ~80 overlap,
  descending paragraph → sentence → hard cut only as far as needed.
- **Vector store** is float32 BLOBs in SQLite with brute-force NumPy cosine:
  exact, reproducible, and fast at this scale. An ANN index is the upgrade path.
- **A relevance threshold** means an unanswerable question gets "I couldn't
  find that" rather than an improvised answer.
- **No LangChain** — the pipeline is a handful of readable functions.

## Deliberately left out

Auth, multi-user, streaming, reranking and hybrid search, retries, containers
and orchestration. Scope matches the assignment's stated 6–12 hour intent.
