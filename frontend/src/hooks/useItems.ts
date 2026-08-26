import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { Item } from "../types";

const POLL_INTERVAL_MS = 2000;

/**
 * The saved-items list, kept live while ingestion is in flight.
 *
 * Because /ingest is asynchronous, a freshly added item lands as 'processing'
 * and only becomes searchable once the worker finishes. So the list polls —
 * but only while something is actually processing. An idle inbox issues no
 * requests at all, which keeps the network tab honest and makes the polling
 * visible as a deliberate choice rather than a background timer nobody owns.
 */
export function useItems() {
  const [items, setItems] = useState<Item[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setItems(await api.listItems());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load items");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const hasProcessing = items.some((item) => item.status === "processing");

  useEffect(() => {
    if (!hasProcessing) return;

    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasProcessing, refresh]);

  return { items, isLoading, error, refresh, isPolling: hasProcessing };
}
