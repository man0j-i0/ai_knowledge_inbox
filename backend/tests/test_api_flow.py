"""End-to-end wiring: /ingest -> background worker -> /items -> /query.

The two OpenAI calls are stubbed with deterministic fakes, so this exercises
the real queue, worker, status lifecycle, SQLite layer, chunker, retrieval and
routes without a network call or an API key. The unit tests cover the pure
functions; this is the test that catches a broken pipeline.
"""
import re
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.lib import embeddings, llm, url_fetcher
from app.lib.url_fetcher import UrlFetchError
from app.main import app
from app.services.rag import NO_ANSWER

FAKE_DIM = 64


def _fake_vector(text: str) -> list[float]:
    """Bag-of-words hashing: texts sharing words get similar vectors, which is
    enough to exercise retrieval meaningfully without calling OpenAI."""
    vec = np.zeros(FAKE_DIM, dtype=np.float32)
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vec[hash(word) % FAKE_DIM] += 1.0
    return vec.tolist()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "similarity_threshold", 0.0)

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [_fake_vector(t) for t in texts]

    async def fake_embed_query(text: str) -> list[float]:
        return _fake_vector(text)

    async def fake_generate_answer(question: str, context_blocks: list[str]) -> str:
        return f"Answer drawn from {len(context_blocks)} chunk(s). [1]"

    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(embeddings, "embed_query", fake_embed_query)
    monkeypatch.setattr(llm, "generate_answer", fake_generate_answer)

    with TestClient(app) as test_client:
        yield test_client


def _wait_for_status(client, item_id: str, expected: str, timeout: float = 5.0) -> dict:
    """Ingestion is asynchronous by design, so the test polls /items the same
    way the frontend does."""
    item = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        item = next(
            (i for i in client.get("/items").json() if i["id"] == item_id), None
        )
        if item and item["status"] == expected:
            return item
        time.sleep(0.05)
    raise AssertionError(f"item {item_id} never reached '{expected}' (last: {item})")


def test_health_is_ok(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_note_is_ingested_asynchronously_then_becomes_queryable(client):
    response = client.post(
        "/ingest",
        json={
            "type": "note",
            "content": "The capital of France is Paris. It sits on the river Seine.",
        },
    )

    assert response.status_code == 202, "ingest must accept and defer, not block"
    assert response.json()["status"] == "processing"
    item_id = response.json()["id"]

    item = _wait_for_status(client, item_id, "ready")
    assert item["type"] == "note"
    assert item["chunk_count"] >= 1
    assert item["error"] is None

    answer = client.post("/query", json={"question": "What is the capital of France?"})
    assert answer.status_code == 200

    body = answer.json()
    assert body["sources"], "a matching note should produce at least one source"
    assert body["sources"][0]["item_id"] == item_id
    assert "Paris" in body["sources"][0]["snippet"]


def test_failed_url_ingest_records_a_readable_error(client, monkeypatch):
    async def failing_fetch(url: str):
        raise UrlFetchError("https://example.com/missing returned HTTP 404")

    monkeypatch.setattr(url_fetcher, "fetch_and_extract", failing_fetch)

    response = client.post(
        "/ingest", json={"type": "url", "url": "https://example.com/missing"}
    )
    assert response.status_code == 202

    item = _wait_for_status(client, response.json()["id"], "failed")
    assert "404" in item["error"], "the failure reason must reach the client"


def test_successful_url_ingest_uses_the_extracted_title(client, monkeypatch):
    async def fake_fetch(url: str):
        return "Real Page Title", "Ferrets are small domesticated mustelids."

    monkeypatch.setattr(url_fetcher, "fetch_and_extract", fake_fetch)

    response = client.post(
        "/ingest", json={"type": "url", "url": "https://example.com/ferrets"}
    )
    item = _wait_for_status(client, response.json()["id"], "ready")

    assert item["title"] == "Real Page Title"
    assert item["source"] == "https://example.com/ferrets"


def test_query_against_an_empty_inbox_says_so(client):
    body = client.post("/query", json={"question": "Anything at all?"}).json()

    assert body["answer"] == NO_ANSWER
    assert body["sources"] == []


def test_query_below_the_relevance_threshold_refuses_to_answer(client, monkeypatch):
    ingested = client.post(
        "/ingest", json={"type": "note", "content": "Ferrets are mustelids."}
    )
    _wait_for_status(client, ingested.json()["id"], "ready")

    # Nothing can clear a threshold of 0.99, so this exercises the guard that
    # stops the model from answering from thin air.
    monkeypatch.setattr(settings, "similarity_threshold", 0.99)
    body = client.post(
        "/query", json={"question": "Explain quantum chromodynamics."}
    ).json()

    assert body["answer"] == NO_ANSWER
    assert body["sources"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "note"},                    # note without content
        {"type": "note", "content": "   "},  # whitespace-only content
        {"type": "url"},                     # url without url
        {"type": "pdf", "content": "x"},     # unsupported source type
        {},                                  # nothing at all
    ],
)
def test_invalid_ingest_payloads_are_rejected(client, payload):
    assert client.post("/ingest", json=payload).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},            # empty question
        {},                          # missing question
        {"question": "hi", "top_k": 0},    # below the allowed range
        {"question": "hi", "top_k": 99},   # above the allowed range
    ],
)
def test_invalid_query_payloads_are_rejected(client, payload):
    assert client.post("/query", json=payload).status_code == 422
