"""Thin async wrapper over OpenAI embeddings. Native async -> safe to await
from the ingestion worker without blocking the event loop."""
from openai import AsyncOpenAI

from app.config import settings

_client = AsyncOpenAI(api_key=settings.openai_api_key)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    resp = await _client.embeddings.create(model=settings.embedding_model, input=texts)
    return [d.embedding for d in resp.data]


async def embed_query(text: str) -> list[float]:
    return (await embed_texts([text]))[0]
