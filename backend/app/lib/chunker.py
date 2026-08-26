"""Chunking strategy: recursive, boundary-aware, token-based.

Why this shape:
  * Embeddings degrade at both extremes. Tiny chunks lose the surrounding
    context that makes them findable; huge chunks average a specific fact away
    into a vague topic vector and waste prompt budget on irrelevant text.
  * So we target ~settings.chunk_size_tokens and only cut at natural
    boundaries: paragraphs first, then sentences, and only as a last resort a
    hard token cut for a single unit that is itself oversized.
  * Consecutive chunks share ~settings.chunk_overlap_tokens, so a fact that
    straddles a boundary survives intact in at least one chunk.
  * A short note stays exactly one chunk. Splitting is never forced.

Chunk size is a target, not a hard ceiling: a chunk carrying an overlap prefix
can run up to ~1.5x the target. That is well inside the embedding model's
context window, and keeping units whole matters more than an exact size.

Pure function, no I/O, which is why tests/test_chunker.py stays trivial.
"""
import re

import tiktoken

from app.config import settings

_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

_encoder = None


def _get_encoder():
    """Lazy so importing this module never triggers a BPE download."""
    global _encoder
    if _encoder is None:
        try:
            _encoder = tiktoken.encoding_for_model(settings.embedding_model)
        except KeyError:
            _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    return len(_get_encoder().encode(text))


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping, boundary-aligned chunks. Order preserved."""
    text = (text or "").strip()
    if not text:
        return []

    max_tokens = settings.chunk_size_tokens
    # Cap overlap at half a chunk: beyond that, chunks are mostly duplicates of
    # each other and retrieval starts returning the same passage twice.
    overlap_tokens = max(0, min(settings.chunk_overlap_tokens, max_tokens // 2))

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for unit in _split_into_units(text, max_tokens):
        unit_tokens = count_tokens(unit)

        if current and current_tokens + unit_tokens > max_tokens:
            finished = "\n\n".join(current)
            chunks.append(finished)
            prefix = _overlap_prefix(finished, overlap_tokens)
            current = [prefix] if prefix else []
            current_tokens = count_tokens(prefix) if prefix else 0

        current.append(unit)
        current_tokens += unit_tokens

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _split_into_units(text: str, max_tokens: int) -> list[str]:
    """Smallest sensible pieces to assemble chunks from, never larger than
    max_tokens. Paragraph -> sentence -> hard token cut, descending only as far
    as necessary."""
    units: list[str] = []

    for paragraph in _PARAGRAPH_RE.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if count_tokens(paragraph) <= max_tokens:
            units.append(paragraph)
            continue

        for sentence in _SENTENCE_RE.split(paragraph):
            sentence = sentence.strip()
            if not sentence:
                continue
            if count_tokens(sentence) <= max_tokens:
                units.append(sentence)
            else:
                # No natural boundary left (minified text, a wall of prose).
                units.extend(_hard_split(sentence, max_tokens))

    return units


def _hard_split(text: str, max_tokens: int) -> list[str]:
    tokens = _get_encoder().encode(text)
    return [
        _get_encoder().decode(tokens[i:i + max_tokens])
        for i in range(0, len(tokens), max_tokens)
    ]


def _overlap_prefix(text: str, overlap_tokens: int) -> str:
    """The tail of a finished chunk, replayed at the head of the next one."""
    if overlap_tokens <= 0:
        return ""

    encoder = _get_encoder()
    tokens = encoder.encode(text)
    if len(tokens) <= overlap_tokens:
        return text

    tail = encoder.decode(tokens[-overlap_tokens:])

    # Snap forward to a clean boundary so the overlap doesn't open mid-word.
    boundary = _SENTENCE_RE.search(tail)
    if boundary:
        return tail[boundary.end():].strip() or tail.strip()
    _, _, after_first_space = tail.partition(" ")
    return (after_first_space or tail).strip()
