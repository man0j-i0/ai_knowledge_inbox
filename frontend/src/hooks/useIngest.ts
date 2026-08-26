import { useCallback, useState } from "react";

import { api } from "../api/client";
import type { IngestRequest } from "../types";

/**
 * Submits a note or URL. Resolves to whether it was accepted, so the form can
 * decide whether to clear itself — a rejected submission should keep what the
 * user typed rather than throwing it away.
 */
export function useIngest(onAccepted: () => void) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(
    async (body: IngestRequest): Promise<boolean> => {
      setIsSubmitting(true);
      setError(null);
      try {
        await api.ingest(body);
        onAccepted();
        return true;
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Failed to save");
        return false;
      } finally {
        setIsSubmitting(false);
      }
    },
    [onAccepted],
  );

  return { submit, isSubmitting, error };
}
