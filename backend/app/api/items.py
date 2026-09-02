"""GET /items — list saved items with their processing status and chunk count.
DELETE /items/{item_id} — remove an item and everything indexed from it."""
from fastapi import APIRouter, HTTPException, Response, status

from app.db import repository as repo
from app.logging_config import log
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


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: str) -> Response:
    """204 on success, 404 if it was never there.

    Deleting an item that is still `processing` is allowed. The worker may
    already hold its id, but it re-reads the row before doing anything and
    stops when it finds nothing, so the delete simply wins the race.
    """
    if not repo.delete_item(item_id):
        raise HTTPException(status_code=404, detail=f"No item with id {item_id}")

    log.info("item.deleted", item_id=item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
