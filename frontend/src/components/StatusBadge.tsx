import type { ItemStatus } from "../types";

const LABELS: Record<ItemStatus, string> = {
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: ItemStatus }) {
  return (
    <span className={`badge badge--${status}`}>
      {status === "processing" && <span className="spinner" aria-hidden="true" />}
      {LABELS[status]}
    </span>
  );
}
