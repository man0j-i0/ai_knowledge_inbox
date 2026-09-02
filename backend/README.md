# AI Knowledge Inbox - Backend

FastAPI service. Takes notes and URLs, indexes them, and answers questions about
them with citations.

## Running it

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # put a real LLM_API_KEY in it
uvicorn app.main:app --reload
```

Docs at http://localhost:8000/docs, health check at /health.

## Which model provider

The client is the OpenAI SDK pointed at whatever `LLM_BASE_URL` says, so
switching providers is config, not code. `.env.example` has blocks for Gemini
and OpenAI. Groq or a local Ollama would work too.

It defaults to Gemini because the free tier doesn't need a card. I picked the
specific models by testing them, not by reading the docs:

| Setting | Value | Why |
|---|---|---|
| `LLM_MODEL` | `gemini-3.6-flash` | 2.5s per answer. `gemini-2.5-flash` is retired for new keys. `gemini-3.7-flash` and `gemini-flash-latest` both took over 45 seconds because they reason before answering. |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Free, and it lets you ask for a specific vector size. |
| `EMBEDDING_DIMENSIONS` | `1536` | It returns 3072 by default. Halving it halves storage and halves the work per query. It's a Matryoshka model so the shorter vector still means something. |

Two things worth knowing.

**Pin the version.** `gemini-flash-latest` sounds sensible and is a trap. It
currently points at a reasoning model, so using it would silently turn a 2.5
second answer into a 45 second one with no code change on my side.

**Changing the embedding model invalidates everything already stored.** Vectors
from different models aren't comparable, and if the dimensions change too then
retrieval just crashes. There's no migration for this. It's on the gaps list.

## Tests

```bash
pytest
```

46 tests. No network, no API key needed. The model calls are stubbed with fake
vectors, so the tests still exercise the real queue, worker, status transitions,
database and routes.

- `test_chunker.py` - boundaries, overlap, size limits, empty input
- `test_similarity.py` - cosine maths, ranking order, doesn't mutate its input
- `test_repository.py` - re-processing an item doesn't duplicate its chunks,
  only `ready` items are searchable, a successful retry clears the old error
- `test_url_fetcher.py` - a real article gets through, a teaser page doesn't
- delete is covered in both: cascade behaviour in the repository suite, and
  `204` / `404` / deleting mid-ingest in the flow suite
- `test_api_flow.py` - ingest through to query, plus the failure paths

## Endpoints

| Method | Path      | What it does                                     |
|--------|-----------|--------------------------------------------------|
| POST   | `/ingest` | Save a note or URL. `202` plus the item id.      |
| GET    | `/items`  | Everything saved, with status and chunk count.   |
| POST   | `/query`  | Ask a question, get an answer and sources.       |
| DELETE | `/items/{item_id}` | Remove an item. `204`, or `404` if unknown. |

`/ingest` returns `202` rather than `201` because the item exists but isn't
searchable yet. Clients poll `/items` to watch it go `processing` to `ready` or
`failed`. Bad input gets a `422` naming the field.

## How it fits together

```
React --REST--> FastAPI --> SQLite (items, chunks + embeddings)
                   |
                   +-- POST /ingest --> create item (processing)
                   |                    enqueue(item_id) --> 202
                   |
                   +-- asyncio.Queue --> worker
                          fetch (httpx), extract (trafilatura, in a thread),
                          chunk, embed, store, mark ready
                          on any error: mark failed with the reason

query: embed question, cosine over chunks, apply threshold,
       number the context, call the model, return answer + sources
```

The layers are strict. `api/` only speaks HTTP. `services/` orchestrates.
`lib/` holds small single-purpose helpers. `db/repository.py` owns every line of
SQL. Nothing reaches past its neighbour.

## Decisions and tradeoffs

**Background ingestion with an in-memory queue.** `/ingest` returns immediately
and a single worker does the work. I didn't reach for Celery or Redis because
this is a single-user app and that's a lot of moving parts to buy nothing. The
real cost is durability: kill the process and the queue is gone. So
`recover_orphaned_items()` runs at startup and re-queues anything stuck in
`processing`. In production you'd want a real queue with retries and a
dead-letter path.

**One worker, not a pool.** Ordering stays simple and I never hammer the
provider's rate limit. The price is throughput, and one slow URL holds up
everything behind it. Acceptable for one user.

**Nothing blocks the event loop.** The model calls and the HTTP fetch are async.
`trafilatura` isn't, and parsing a big page takes real CPU time, so it runs via
`asyncio.to_thread`. Get this wrong and you've written `async def` everywhere
while still freezing the server on every ingest.

**Three states, not two.** `failed` carries the reason all the way to the UI:
"returned HTTP 404", "only 283 characters of readable text were extracted".
Without it a broken link sits on `processing` forever and the user is left
guessing.

**Chunking.** Split on paragraphs, fall back to sentences, and only cut
mid-sentence when there's no choice. Target 600 tokens with 80 of overlap.
Chunks that are too small lose the context that makes them findable. Too big and
the one useful sentence gets averaged into a vague topic vector that also eats
prompt budget. Overlap means a fact sitting on a boundary survives whole in at
least one chunk. A short note stays as one chunk.

**Vectors as float32 blobs in SQLite, compared with NumPy.** Exact, no index to
tune, and I can print the scores when something looks wrong. What breaks first
isn't the maths, it's that every query reloads and deserialises every vector.
Fine at a few thousand chunks, painful past ten thousand. The fix order would be
to cache the matrix in memory, then move to `sqlite-vec`, then pgvector.

**The relevance threshold, which is measured rather than guessed.** If nothing
clears `SIMILARITY_THRESHOLD` the API says so and never calls the model at all,
which is cheaper and safer than asking it to decline politely. Here's what the
scores actually looked like against a single note about a project called Falcon:

| Question | Score |
|---|---|
| "Who is the technical lead on Project Falcon?" | 0.749 |
| "Where will the Falcon pilot run?" | 0.708 |
| "What is retrieval-augmented generation?" | 0.481 |
| "What is the recipe for sourdough bread?" | 0.408 |
| "How do I renew a Canadian passport?" | 0.401 |

So this model sits around 0.40 even for text with nothing to do with the
question, and lands at 0.70+ on a genuine match. 0.60 goes in the gap.

I had it at 0.35 originally, which is a sane default for OpenAI's embeddings and
completely wrong for this one. Everything got through the filter. The answers
still looked correct, because the system prompt caught what the threshold let
past, which is exactly why I didn't spot it until I logged the scores. A
threshold belongs to the embedding model, not to the app.

**Deleting is a hard delete, not a soft one.** The row goes, and the chunks go
with it through `ON DELETE CASCADE`. That cascade only fires because
`get_connection()` sets `PRAGMA foreign_keys = ON` - SQLite ignores foreign keys
by default, which would have quietly left orphaned chunks behind and kept a
deleted item answering questions. Deleting something mid-ingest is allowed too:
the worker re-reads the row before it does anything and stops when it finds
nothing there, so the delete just wins the race.

**Citations.** Retrieved chunks get numbered in the prompt and the model is told
to cite by number. The response ships the same numbering, so the UI can line the
`[1]` in the answer up with the passage it came from.

**A database connection per unit of work.** `get_connection()` commits, rolls
back on error, and always closes. `with sqlite3.connect(...)` on its own commits
but never closes, which leaks a handle every request. Opening a fresh connection
each time also sidesteps sqlite3's same-thread rule, which matters because the
worker isn't on the request thread.

**No LangChain.** The whole pipeline is chunk, embed, retrieve, prompt. Four
readable functions beat a framework whose source I'd have to go read the first
time retrieval returns something stupid.

## URL ingestion in practice

`trafilatura` does a good job on real pages. The FastAPI docs homepage comes out
as about 14k characters of clean text with the title intact.

Two things I ran into.

**Some sites just say no.** Wikipedia returns 403 to anything programmatic. I
tried a full Chrome User-Agent against five sites and got identical status codes
either way, so impersonating a browser buys nothing and the fetcher identifies
itself honestly instead. Sites like that need a headless browser or a reader
API, which felt out of scope here.

**A successful fetch isn't the same as a usable article.** Feeding it a link
aggregator worked perfectly and produced a completely useless item: 283
characters of headline and teaser, stored as a healthy `ready` item that could
never answer anything. That's a silent failure dressed up as a success, which is
worse than a loud one. Anything under `MIN_EXTRACTED_CHARS` now fails with a
message telling you to link to the article rather than the index. Notes are
exempt, because a two-word note is fine and a two-word article isn't.

## Debugging it

Logs are JSON via `structlog`. A request id is bound once in middleware and
appears on every line for that request, including work the background worker
does later. It also comes back as the `X-Request-ID` header.

Useful events: `ingest.start`, `ingest.ready`, `ingest.failed`, `ingest.recover`,
`query.scores`.

`query.scores` is the one that earns its keep. When retrieval feels wrong it
tells you straight away whether the threshold is too high, nothing relevant was
stored, or the content never got indexed at all. Three different problems that
look identical from the outside.

## Known gaps

Roughly in the order I'd fix them.

1. **No retries.** One transient 429 or 500 kills an item permanently. The two
   kinds of 429 need opposite handling, too: rate limiting should back off and
   retry, quota exhaustion can never succeed and should fail immediately. Same
   status code, so you have to read the error body.
2. **Every query reloads every vector**, as above.
3. **Single process only.** `uvicorn --workers 2` would give each process its
   own queue and run the recovery sweep twice.
4. **No embedding model versioning**, so swapping models quietly invalidates
   what's stored.
5. **SSRF.** `/ingest` will fetch any URL you give it, including internal
   addresses.
6. **No re-index or pagination endpoints.** Re-index would be easy now, since
   processing is idempotent and the original text is kept.
7. **No evaluation harness.** Retrieval quality is unmeasured beyond the
   threshold calibration above.
8. **That threshold came from a small corpus.** The gap between 0.48 and 0.71
   might narrow with more content in there.

## Left out on purpose

Auth, multi-user, streaming, reranking, hybrid search, Docker. The brief asked
for 6 to 12 hours and said not to build infrastructure theatre, so these are
paragraphs above rather than directories of code.
