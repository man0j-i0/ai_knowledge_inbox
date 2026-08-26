import { useState } from "react";

import { useIngest } from "../hooks/useIngest";
import type { SourceType } from "../types";
import { ErrorBanner } from "./ErrorBanner";

export function AddItemForm({ onAccepted }: { onAccepted: () => void }) {
  const [type, setType] = useState<SourceType>("note");
  const [note, setNote] = useState("");
  const [url, setUrl] = useState("");

  const { submit, isSubmitting, error } = useIngest(onAccepted);

  const value = type === "note" ? note : url;
  const canSubmit = value.trim().length > 0 && !isSubmitting;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;

    const accepted =
      type === "note"
        ? await submit({ type: "note", content: note })
        : await submit({ type: "url", url: url.trim() });

    // Only clear on success, so a rejected submission keeps the user's text.
    if (accepted) {
      setNote("");
      setUrl("");
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2>Add to inbox</h2>

      <div className="tabs" role="tablist">
        {(["note", "url"] as const).map((option) => (
          <button
            key={option}
            type="button"
            role="tab"
            aria-selected={type === option}
            className={`tab ${type === option ? "tab--active" : ""}`}
            onClick={() => setType(option)}
          >
            {option === "note" ? "Note" : "URL"}
          </button>
        ))}
      </div>

      {type === "note" ? (
        <textarea
          className="input"
          rows={5}
          placeholder="Paste or type a note…"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          disabled={isSubmitting}
        />
      ) : (
        <input
          className="input"
          type="url"
          placeholder="https://example.com/article"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          disabled={isSubmitting}
        />
      )}

      <ErrorBanner message={error} />

      <div className="form-footer">
        <button className="button" type="submit" disabled={!canSubmit}>
          {isSubmitting ? "Saving…" : "Save"}
        </button>
        <span className="hint">
          {type === "url"
            ? "The page is fetched and stripped to its article text in the background."
            : "Indexed in the background — it becomes searchable once ready."}
        </span>
      </div>
    </form>
  );
}
