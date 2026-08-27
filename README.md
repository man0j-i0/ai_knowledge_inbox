# AI Knowledge Inbox

Save notes and links, then ask questions across everything you've saved. Answers
come back with citations to the source text.

FastAPI on the backend, React on the frontend, a small RAG pipeline in between.

## Running it

Two terminals, and you'll need an API key.

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # put a real LLM_API_KEY in it
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. Use `localhost`, not `127.0.0.1`, because the
backend only allows that exact origin for CORS.

API docs are at http://localhost:8000/docs.

### About the API key

It talks to anything that speaks the OpenAI API format. `.env.example` has
ready-made blocks for Google Gemini and OpenAI, and Groq or a local Ollama would
work the same way. It ships pointed at Gemini because the free tier doesn't need
a card. `backend/README.md` explains which models and why.

## How it works

```
                    +------------------------------------------+
  React (hooks)     |  FastAPI                                 |
   add note/URL --> |   POST /ingest --> create item, enqueue  |--> 202
   items + status <-|   GET  /items  --> list + status         |
   ask question --> |   POST /query  --> RAG pipeline          |
   answer+sources <-|                                          |
                    +-------+--------------------------+-------+
                            |                          |
         +------------------v-----+   +----------------v---------+
         | ingestion worker       |   | query pipeline           |
         | (asyncio.Queue)        |   | embed question           |
         |  fetch  (httpx)        |   | cosine over all chunks   |
         |  extract (trafilatura) |   | threshold + top-k        |
         |  chunk                 |   | numbered context -> LLM  |
         |  embed                 |   | answer + cited sources   |
         |  -> ready | failed     |   +----------------+---------+
         +------------------+-----+                    |
                     +------v-----------------------------+
                     | SQLite: items, chunks + embeddings  |
                     +-------------------------------------+
```

The important bit is that ingestion happens in the background. `POST /ingest`
saves the item and returns `202` straight away, then a worker does the slow part
(fetching, extracting, chunking, embedding) and marks the item `ready`, or
`failed` with the reason. Fetching a URL can take ten seconds, so doing that
inside the request would make the app feel broken.

The frontend polls `/items` while anything is still processing and stops once
the list is idle.

## API

| Method | Path      | What it does                                             |
|--------|-----------|----------------------------------------------------------|
| POST   | `/ingest` | Save a note or URL. Returns `202` with the new item's id. |
| GET    | `/items`  | List saved items with status, chunk count, and error.    |
| POST   | `/query`  | Ask a question. Returns an answer and its sources.       |
| GET    | `/health` | Liveness check.                                          |

Bad input gets a `422` naming the field that's wrong. Every response has an
`X-Request-ID` header, and the same id shows up in the logs, so you can trace one
request through the API and the background worker.

## Layout

```
backend/
  app/
    api/        HTTP only, no logic
    services/   ingestion pipeline, RAG pipeline
    lib/        chunker, similarity, fetcher, model clients
    db/         schema and all the SQL
  tests/        40 tests
frontend/
  src/
    api/        the only file that touches the network
    hooks/      useItems (polls), useIngest, useAsk
    components/ form, item list, ask panel, answer + sources
```

## Tests

```bash
cd backend && pytest          # 40 tests, no network, no API key needed
cd frontend && npm run build  # typecheck + build
```

The model calls are stubbed with fake vectors, so the tests still run the real
queue, worker, database and routes. They cover the failure paths too: a URL that
404s, a page with no article on it, an empty inbox, a question that matches
nothing, and every shape of bad request.

## Decisions worth explaining

The longer version is in [`backend/README.md`](backend/README.md). Short version:

**Background ingestion using an in-memory queue.** Not Celery or Redis, because
this is a single-user app and that would be a lot of infrastructure for no
benefit. The catch is durability: if the process dies, anything in the queue is
gone. So on startup it looks for items stuck in `processing` and re-queues them.

**Nothing blocks the event loop.** The model and HTTP clients are async.
Content extraction isn't, so it runs in a thread. Otherwise a single slow ingest
would freeze the whole API, which defeats the point of doing it in the
background.

**Three states, not two.** `failed` carries the reason with it. Without that, a
dead link just sits on `processing` forever and you have no idea why.

**Chunking** splits on paragraphs first, then sentences, and only cuts mid-text
if it has to. Around 600 tokens with 80 tokens of overlap. Small chunks lose the
context that makes them findable, big ones bury the useful sentence in noise.

**Vectors live in SQLite as float32 blobs** and I compare them with NumPy. At
this size that's exact, fast, and easy to debug. The first thing that breaks at
scale is that every query reloads every vector, which is fine for thousands of
chunks and not fine for hundreds of thousands.

**There's a relevance floor.** If nothing scores above it, you get "I couldn't
find that" and the model never gets called, so those queries come back in under
half a second. The number came from logging real scores, not from guessing. See
the backend README, it's a good story.

**No LangChain.** Chunk, embed, retrieve, prompt. That's four functions I can
read and explain.

## Not included

No auth, no multi-user, no streaming, no reranking, no Docker. The brief said to
avoid that stuff and I'd rather explain the tradeoffs than build infrastructure
nobody asked for.
