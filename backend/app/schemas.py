"""Pydantic request/response contracts. These ARE the API's input validation."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SourceType(str, Enum):
    note = "note"
    url = "url"


class ItemStatus(str, Enum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


class IngestRequest(BaseModel):
    type: SourceType
    content: Optional[str] = Field(default=None, description="Required when type == note")
    url: Optional[str] = Field(default=None, description="Required when type == url")

    @model_validator(mode="after")
    def _require_matching_payload(self) -> "IngestRequest":
        if self.type is SourceType.note and not (self.content and self.content.strip()):
            raise ValueError("content is required and cannot be empty for a note")
        if self.type is SourceType.url and not (self.url and self.url.strip()):
            raise ValueError("url is required for url ingestion")
        return self


class IngestResponse(BaseModel):
    id: str
    status: ItemStatus


class ItemResponse(BaseModel):
    id: str
    type: SourceType
    title: str
    source: Optional[str] = None
    status: ItemStatus
    error: Optional[str] = None
    chunk_count: int = 0
    created_at: datetime


class Source(BaseModel):
    item_id: str
    title: str
    url: Optional[str] = None
    snippet: str
    score: float


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: Optional[int] = Field(default=None, ge=1, le=20)


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
