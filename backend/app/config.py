"""Typed application settings, loaded from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Model provider. Anything speaking the OpenAI wire format works here —
    # OpenAI itself, Gemini's compatibility endpoint, Groq, or a local Ollama.
    # Leave llm_base_url unset for OpenAI.
    llm_api_key: str
    llm_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4o-mini"
    # Only sent when set: not every provider accepts an output dimension.
    embedding_dimensions: int | None = None

    # Storage
    db_path: str = "knowledge_inbox.db"

    # Chunking
    chunk_size_tokens: int = 600
    chunk_overlap_tokens: int = 80

    # Retrieval
    retrieval_top_k: int = 5
    # Model-specific, and measured rather than guessed: gemini-embedding-001
    # scores ~0.40 even for completely unrelated text, while genuinely relevant
    # chunks land at 0.70+. 0.60 sits in that gap. A different embedding model
    # needs this re-measured — see README.
    similarity_threshold: float = 0.60

    # URL ingestion
    url_fetch_timeout_seconds: float = 10.0
    max_content_chars: int = 200_000


settings = Settings()
