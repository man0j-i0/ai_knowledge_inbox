"""Thin async wrapper over the embeddings endpoint. Native async -> safe to
await from the ingestion worker without blocking the event loop."""
from app.config import settings
from app.lib.llm_client import client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    # Some models let you ask for a shorter vector (halving storage and the
    # per-query dot product); others reject the parameter outright, so it is
    # only sent when explicitly configured.
    options = {}
    if settings.embedding_dimensions is not None:
        options["dimensions"] = settings.embedding_dimensions

    response = await client.embeddings.create(
        model=settings.embedding_model, input=texts, **options
    )
    return [item.embedding for item in response.data]


async def embed_query(text: str) -> list[float]:
    return (await embed_texts([text]))[0]
