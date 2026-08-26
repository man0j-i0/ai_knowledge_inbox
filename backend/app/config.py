"""Typed application settings, loaded from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # OpenAI
    openai_api_key: str
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4o-mini"
    embedding_dim: int = 1536

    # Storage
    db_path: str = "knowledge_inbox.db"

    # Chunking
    chunk_size_tokens: int = 600
    chunk_overlap_tokens: int = 80

    # Retrieval
    retrieval_top_k: int = 5
    similarity_threshold: float = 0.35  # tune empirically — see README

    # URL ingestion
    url_fetch_timeout_seconds: float = 10.0
    max_content_chars: int = 200_000


settings = Settings()
