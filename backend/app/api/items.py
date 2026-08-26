"""GET /items — list saved items with their processing status and chunk count."""
from fastapi import APIRouter

from app.db import repository as repo
from app.schemas import ItemResponse

router = APIRouter()


@router.get("/items", response_model=list[ItemResponse])
async def list_items() -> list[ItemResponse]:
    return [
        ItemResponse(
            id=row["id"], type=row["type"], title=row["title"],
            source=row["source"], status=row["status"], error=row["error"],
            chunk_count=row["chunk_count"], created_at=row["created_at"],
        )
        for row in repo.list_items()
    ]
