import { useState } from "react";

import type { Item } from "../types";
import { ErrorBanner } from "./ErrorBanner";
import { StatusBadge } from "./StatusBadge";

function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString();
}

/**
 * Two clicks to delete. There is no undo and the embeddings have to be
 * regenerated to get an item back, so a misclick is expensive enough to be
 * worth one extra click — and cheaper than a modal.
 */
function RemoveButton({ onConfirm }: { onConfirm: () => void }) {
  const [isArmed, setIsArmed] = useState(false);

  if (!isArmed) {
    return (
      <button
        type="button"
        className="remove"
        aria-label="Remove item"
        onClick={() => setIsArmed(true)}
      >
        ×
      </button>
    );
  }

  return (
    <span className="remove-confirm">
      <button type="button" className="remove remove--yes" onClick={onConfirm}>
        Remove
      </button>
      <button type="button" className="remove" onClick={() => setIsArmed(false)}>
        Cancel
      </button>
    </span>
  );
}

interface ItemRowProps {
  item: Item;
  onRemove: (itemId: string) => void;
}

function ItemRow({ item, onRemove }: ItemRowProps) {
  return (
    <li className="item">
      <div className="item__head">
        <span className="item__title" title={item.title}>
          {item.title}
        </span>
        <StatusBadge status={item.status} />
        <RemoveButton onConfirm={() => onRemove(item.id)} />
      </div>

      <div className="item__meta">
        <span className="tag">{item.type}</span>
        <span>{formatTimestamp(item.created_at)}</span>
        {item.status === "ready" && (
          <span>
            {item.chunk_count} {item.chunk_count === 1 ? "chunk" : "chunks"}
          </span>
        )}
        {item.source && (
          <a href={item.source} target="_blank" rel="noreferrer noopener">
            source
          </a>
        )}
      </div>

      {/* The reason a failure happened is the whole point of tracking one. */}
      {item.status === "failed" && item.error && (
        <p className="item__error">{item.error}</p>
      )}
    </li>
  );
}

interface ItemListProps {
  items: Item[];
  isLoading: boolean;
  error: string | null;
  isPolling: boolean;
  onRemove: (itemId: string) => void;
}

export function ItemList({ items, isLoading, error, isPolling, onRemove }: ItemListProps) {
  return (
    <section className="card">
      <div className="card__head">
        <h2>Saved items ({items.length})</h2>
        {isPolling && <span className="hint">refreshing…</span>}
      </div>

      <ErrorBanner message={error} />

      {isLoading ? (
        <p className="empty">Loading…</p>
      ) : items.length === 0 ? (
        <p className="empty">Nothing saved yet. Add a note or URL to get started.</p>
      ) : (
        <ul className="item-list">
          {items.map((item) => (
            <ItemRow key={item.id} item={item} onRemove={onRemove} />
          ))}
        </ul>
      )}
    </section>
  );
}
