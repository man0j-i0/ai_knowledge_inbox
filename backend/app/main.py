"""App wiring: lifespan starts the ingestion worker + recovers orphans;
middleware attaches a request id and structured logging; routers are mounted."""
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import ingest, items, query
from app.db.database import init_db
from app.logging_config import configure_logging, log
from app.services import ingestion


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    ingestion.start_worker()
    await ingestion.recover_orphaned_items()
    log.info("app.startup")
    yield
    await ingestion.stop_worker()
    log.info("app.shutdown")


app = FastAPI(title="AI Knowledge Inbox", lifespan=lifespan)

# Vite dev server origin; adjust for your frontend port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        structlog.contextvars.clear_contextvars()


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(ingest.router)
app.include_router(items.router)
app.include_router(query.router)
