import { useCallback, useRef, useState } from "react";

import { api } from "../api/client";
import type { QueryResponse } from "../types";

/**
 * Asks a question and holds the most recent answer.
 *
 * Answers arrive out of order if the user asks again before the first returns,
 * so each request carries a sequence number and a stale response is discarded
 * rather than overwriting a newer answer.
 */
export function useAsk() {
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [askedQuestion, setAskedQuestion] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const latestRequestId = useRef(0);

  const ask = useCallback(async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed) return;

    const requestId = ++latestRequestId.current;
    setIsAsking(true);
    setError(null);

    try {
      const response = await api.ask({ question: trimmed });
      if (requestId !== latestRequestId.current) return; // superseded
      setResult(response);
      setAskedQuestion(trimmed);
    } catch (caught) {
      if (requestId !== latestRequestId.current) return;
      setError(caught instanceof Error ? caught.message : "Failed to get an answer");
      setResult(null);
    } finally {
      if (requestId === latestRequestId.current) setIsAsking(false);
    }
  }, []);

  return { result, askedQuestion, isAsking, error, ask };
}
