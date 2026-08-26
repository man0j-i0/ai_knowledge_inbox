"""Tests for lib/similarity.py — retrieval ranking is the one place a silent
maths bug produces plausible-looking but wrong answers, so pin it down."""
import numpy as np
import pytest

from app.lib.similarity import cosine_similarity, top_k


def test_identical_vectors_score_one():
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_orthogonal_vectors_score_zero():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_opposite_vectors_score_minus_one():
    a = np.array([1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, -a) == pytest.approx(-1.0)


def test_magnitude_does_not_affect_score():
    a = np.array([1.0, 1.0], dtype=np.float32)
    assert cosine_similarity(a, a * 100) == pytest.approx(1.0)


def test_zero_vector_scores_zero_not_nan():
    a = np.array([1.0, 0.0], dtype=np.float32)
    zero = np.array([0.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, zero) == 0.0


def test_top_k_returns_k_sorted_desc():
    query = np.array([1.0, 0.0], dtype=np.float32)
    chunks = [
        {"embedding": np.array([1.0, 0.0], dtype=np.float32)},
        {"embedding": np.array([0.0, 1.0], dtype=np.float32)},
        {"embedding": np.array([0.9, 0.1], dtype=np.float32)},
    ]
    result = top_k(query, chunks, k=2)

    assert len(result) == 2
    assert result[0]["score"] >= result[1]["score"]


def test_top_k_scores_match_cosine_similarity():
    query = np.array([1.0, 0.0], dtype=np.float32)
    chunks = [
        {"id": "a", "embedding": np.array([0.9, 0.1], dtype=np.float32)},
        {"id": "b", "embedding": np.array([0.2, 0.9], dtype=np.float32)},
    ]
    by_id = {c["id"]: c for c in chunks}

    for row in top_k(query, chunks, k=2):
        expected = cosine_similarity(query, by_id[row["id"]]["embedding"])
        assert row["score"] == pytest.approx(expected, abs=1e-6)


def test_top_k_preserves_chunk_fields():
    query = np.array([1.0, 0.0], dtype=np.float32)
    chunks = [{"id": "a", "content": "hello", "embedding": query}]

    result = top_k(query, chunks, k=1)

    assert result[0]["id"] == "a"
    assert result[0]["content"] == "hello"
    assert "score" not in chunks[0], "top_k must not mutate its input"


def test_top_k_handles_k_larger_than_corpus_and_empty_input():
    query = np.array([1.0, 0.0], dtype=np.float32)
    chunks = [{"embedding": query}]

    assert len(top_k(query, chunks, k=10)) == 1
    assert top_k(query, [], k=5) == []
    assert top_k(query, chunks, k=0) == []
