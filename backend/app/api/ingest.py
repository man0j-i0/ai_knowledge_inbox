"""POST /ingest — create the item, enqueue background processing, return 202."""
import uuid

from fastapi import APIRouter, status

from app.db import repository as repo
from app.schemas import IngestRequest, IngestResponse, ItemStatus, SourceType
from app.services import ingestion

router = APIRouter()


def _title_from_note(content: str) -> str:
    first_line = content.strip().splitlines()[0] if content.strip() else "Untitled note"
    return first_line[:80] + "…" if len(first_line) > 80 else first_line


@router.post("/ingest", response_model=IngestResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def ingest(req: IngestRequest) -> IngestResponse:
    item_id = str(uuid.uuid4())

    if req.type is SourceType.url:
        # Provisional title; the worker replaces it with the real page title.
        repo.create_item(item_id, SourceType.url, title=req.url,
                         source=req.url, raw_content=None)
    else:
        repo.create_item(item_id, SourceType.note,
                         title=_title_from_note(req.content or ""),
                         source=None, raw_content=req.content)

    await ingestion.enqueue(item_id)
    return IngestResponse(id=item_id, status=ItemStatus.processing)
