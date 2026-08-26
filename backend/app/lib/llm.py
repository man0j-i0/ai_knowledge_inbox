"""Thin async wrapper over the chat model. Model name is config-driven, so
swapping providers/models is a one-line change (see README tradeoffs)."""
from app.config import settings
from app.lib.llm_client import client

SYSTEM_PROMPT = (
    "You answer strictly from the provided context. "
    "Cite the sources you use by their bracket number, e.g. [1], [2]. "
    "If the context does not contain the answer, say you don't have that "
    "information in the saved content. Never use outside knowledge."
)


async def generate_answer(question: str, context_blocks: list[str]) -> str:
    context = "\n\n".join(context_blocks)
    user = f"Context:\n{context}\n\nQuestion: {question}"
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content or ""
