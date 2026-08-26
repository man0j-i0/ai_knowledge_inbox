"""Vector similarity: brute-force cosine over every stored chunk.

At this scale (hundreds to low thousands of chunks) an exhaustive NumPy pass is
sub-millisecond and completely transparent to debug: no index to build, no
recall/latency knob to mistune, and retrieval is exactly reproducible. It is
O(n*d) per query with every vector resident in memory, which is precisely what
breaks first at scale (see README).
"""
import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine of the angle between two vectors, in [-1, 1]. 0 if either is a
    zero vector (undefined angle) rather than a NaN that poisons ranking."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)

    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(a, b) / denominator)


def top_k(query_vec: np.ndarray, chunks: list[dict], k: int) -> list[dict]:
    """Rank chunks against the query vector, highest cosine first.

    chunks: dicts each carrying an 'embedding' vector. Returns at most k
    shallow copies, each annotated with a float 'score' so the RAG service can
    apply its relevance threshold. Inputs are never mutated.
    """
    if not chunks or k <= 0:
        return []

    matrix = np.vstack([np.asarray(c["embedding"], dtype=np.float32) for c in chunks])
    query = np.asarray(query_vec, dtype=np.float32)

    # One matrix-vector product beats a Python loop over cosine_similarity, and
    # the `where` guard keeps a zero vector at score 0 instead of NaN.
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
    scores = np.divide(
        matrix @ query,
        norms,
        out=np.zeros(len(chunks), dtype=np.float32),
        where=norms != 0,
    )

    k = min(k, len(chunks))
    candidates = np.argpartition(-scores, k - 1)[:k]  # O(n) select, then sort k
    ranked = candidates[np.argsort(-scores[candidates])]

    return [{**chunks[i], "score": float(scores[i])} for i in ranked]
