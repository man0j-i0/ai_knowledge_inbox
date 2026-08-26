/**
 * The only module that talks to the network.
 *
 * Its real job is turning failures into something a person can read: a
 * FastAPI 422 arrives as a nested array of field errors, and an unreachable
 * backend arrives as a bare TypeError with no useful message at all. Both
 * become a plain sentence here so no component has to know that.
 */
import type {
  IngestRequest,
  IngestResponse,
  Item,
  QueryRequest,
  QueryResponse,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface ValidationDetail {
  loc?: unknown[];
  msg?: string;
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body.detail;

    if (typeof detail === "string") return detail;

    // 422 from Pydantic: name the offending field rather than showing raw JSON.
    if (Array.isArray(detail)) {
      const parts = (detail as ValidationDetail[]).map((entry) => {
        const field = Array.isArray(entry.loc)
          ? entry.loc.filter((part) => part !== "body").join(".")
          : "";
        const message = entry.msg ?? "is invalid";
        return field ? `${field}: ${message}` : message;
      });
      if (parts.length > 0) return parts.join("; ");
    }
  } catch {
    // Body was not JSON; fall through to the status line.
  }
  return `Request failed (${response.status} ${response.statusText})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${BASE_URL}. Is the backend running?`,
      0,
    );
  }

  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  listItems: () => request<Item[]>("/items"),

  /** Returns 202: the item exists but is not searchable until the worker finishes. */
  ingest: (body: IngestRequest) =>
    request<IngestResponse>("/ingest", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  ask: (body: QueryRequest) =>
    request<QueryResponse>("/query", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
