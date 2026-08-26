import type { Item } from "../types";
import { ErrorBanner } from "./ErrorBanner";
import { StatusBadge } from "./StatusBadge";

function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString();
}

function ItemRow({ item }: { item: Item }) {
  return (
    <li className="item">
      <div className="item__head">
        <span className="item__title" title={item.title}>
          {item.title}
        </span>
        <StatusBadge status={item.status} />
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
}

export function ItemList({ items, isLoading, error, isPolling }: ItemListProps) {
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
            <ItemRow key={item.id} item={item} />
          ))}
        </ul>
      )}
    </section>
  );
}
