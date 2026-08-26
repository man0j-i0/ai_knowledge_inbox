/**
 * Mirrors the Pydantic contracts in backend/app/schemas.py. Field names stay
 * snake_case deliberately: renaming at the boundary buys nothing and makes the
 * two halves harder to diff against each other.
 */

export type SourceType = "note" | "url";

/** Ingestion is asynchronous, so an item is not searchable until it is ready. */
export type ItemStatus = "processing" | "ready" | "failed";

export interface Item {
  id: string;
  type: SourceType;
  title: string;
  source: string | null;
  status: ItemStatus;
  error: string | null;
  chunk_count: number;
  created_at: string;
}

export interface IngestResponse {
  id: string;
  status: ItemStatus;
}

export type IngestRequest =
  | { type: "note"; content: string }
  | { type: "url"; url: string };

export interface Source {
  item_id: string;
  title: string;
  url: string | null;
  snippet: string;
  score: number;
}

export interface QueryResponse {
  answer: string;
  sources: Source[];
}

export interface QueryRequest {
  question: string;
  top_k?: number;
}
