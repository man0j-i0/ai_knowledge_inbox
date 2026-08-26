"""POST /query — retrieve relevant chunks and answer with cited sources."""
from fastapi import APIRouter

from app.schemas import QueryRequest, QueryResponse
from app.services import rag

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    return await rag.answer_question(req.question, req.top_k)
