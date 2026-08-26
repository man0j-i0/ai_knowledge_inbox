"""Retrieval-augmented answering:
embed question -> cosine top-k -> relevance threshold -> prompt -> LLM ->
answer + cited sources."""
import numpy as np

from app.config import settings
from app.db import repository as repo
from app.lib import embeddings, llm, similarity
from app.logging_config import log
from app.schemas import QueryResponse, Source

NO_ANSWER = "I couldn't find relevant information in your saved content."


async def answer_question(question: str, top_k: int | None = None) -> QueryResponse:
    k = top_k or settings.retrieval_top_k

    chunk_rows = repo.get_ready_chunks()
    if not chunk_rows:
        return QueryResponse(answer=NO_ANSWER, sources=[])

    for row in chunk_rows:
        row["embedding"] = repo.blob_to_embedding(row["embedding"])

    query_vec = np.asarray(await embeddings.embed_query(question), dtype=np.float32)
    ranked = similarity.top_k(query_vec, chunk_rows, k)

    # Log real scores so the threshold can be tuned from evidence, not a guess.
    log.info("query.scores", scores=[round(float(r["score"]), 3) for r in ranked])

    relevant = [r for r in ranked if r["score"] >= settings.similarity_threshold]
    if not relevant:
        return QueryResponse(answer=NO_ANSWER, sources=[])

    context_blocks: list[str] = []
    sources: list[Source] = []
    for idx, r in enumerate(relevant, start=1):
        context_blocks.append(f"[{idx}] {r['content']}")
        sources.append(Source(
            item_id=r["item_id"],
            title=r["title"],
            url=r.get("source"),
            snippet=r["content"][:280],
            score=round(float(r["score"]), 3),
        ))

    answer = await llm.generate_answer(question, context_blocks)
    return QueryResponse(answer=answer, sources=sources)
