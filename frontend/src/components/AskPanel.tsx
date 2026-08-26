import { useState } from "react";

import { useAsk } from "../hooks/useAsk";
import { AnswerView } from "./AnswerView";
import { ErrorBanner } from "./ErrorBanner";

export function AskPanel({ readyItemCount }: { readyItemCount: number }) {
  const [question, setQuestion] = useState("");
  const { result, askedQuestion, isAsking, error, ask } = useAsk();

  const canAsk = question.trim().length > 0 && !isAsking;

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (canAsk) void ask(question);
  }

  return (
    <section className="card">
      <h2>Ask your inbox</h2>

      <form className="ask-form" onSubmit={handleSubmit}>
        <input
          className="input"
          type="text"
          placeholder="What do my notes say about…?"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={isAsking}
        />
        <button className="button" type="submit" disabled={!canAsk}>
          {isAsking ? "Thinking…" : "Ask"}
        </button>
      </form>

      {readyItemCount === 0 && (
        <p className="hint">
          Nothing is indexed yet, so there is nothing to search. Add an item first.
        </p>
      )}

      <ErrorBanner message={error} />

      {result && !isAsking && <AnswerView result={result} question={askedQuestion} />}
    </section>
  );
}
