"""One shared client for every model call.

The provider is a base_url, not a code path. OpenAI, Gemini's compatibility
endpoint, Groq and a local Ollama all speak the same wire format, so moving
between them is configuration rather than a rewrite — which is the whole reason
this is a single shared object instead of a client constructed inside each
wrapper.
"""
from openai import AsyncOpenAI

from app.config import settings

# base_url=None falls back to the OpenAI default.
client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
