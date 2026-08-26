"""Tests for lib/chunker.py — the chunker is a pure function, so its behaviour
is worth pinning down exactly: the boundaries it respects and the overlap it
promises are what retrieval quality rests on."""
from app.config import settings
from app.lib.chunker import chunk_text, count_tokens


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _long_text(sentence_count: int = 400) -> str:
    return "\n\n".join(
        f"Sentence number {i} carries its own distinct fact."
        for i in range(sentence_count)
    )


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_note_is_single_chunk():
    assert len(chunk_text("A short note.")) == 1


def test_long_text_splits_into_multiple_chunks():
    text = "para.\n\n" * 500
    assert len(chunk_text(text)) > 1


def test_consecutive_chunks_overlap():
    chunks = chunk_text(_long_text())
    assert len(chunks) > 1

    for earlier, later in zip(chunks, chunks[1:]):
        tail = _normalize(" ".join(earlier.split()[-5:]))
        assert tail in _normalize(later), "chunk boundary lost its overlap"


def test_chunks_stay_near_the_target_size():
    # A chunk may carry an overlap prefix on top of a full unit, so the target
    # is a target — but it must not run away.
    ceiling = settings.chunk_size_tokens + settings.chunk_overlap_tokens + 50
    assert all(count_tokens(c) <= ceiling for c in chunk_text(_long_text()))


def test_paragraph_boundaries_are_preferred_over_mid_sentence_cuts():
    chunks = chunk_text(_long_text())
    # Every chunk should end at the end of a sentence, never mid-word.
    assert all(c.rstrip().endswith(".") for c in chunks)


def test_text_with_no_natural_boundary_is_still_split():
    # One enormous "sentence" with no paragraph or sentence break to cut on.
    wall = "word " * (settings.chunk_size_tokens * 3)
    chunks = chunk_text(wall)
    assert len(chunks) > 1
