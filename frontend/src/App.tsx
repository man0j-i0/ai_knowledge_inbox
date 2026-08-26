import { AddItemForm } from "./components/AddItemForm";
import { AskPanel } from "./components/AskPanel";
import { ItemList } from "./components/ItemList";
import { useItems } from "./hooks/useItems";

/**
 * State lives here because the items list is the only thing two branches of
 * the tree care about: adding an item must refresh it, and the ask panel needs
 * to know whether anything is indexed yet. That is one shared value — far
 * short of what would justify a store or a context.
 */
export default function App() {
  const { items, isLoading, error, refresh, isPolling } = useItems();
  const readyItemCount = items.filter((item) => item.status === "ready").length;

  return (
    <div className="app">
      <header className="header">
        <h1>AI Knowledge Inbox</h1>
        <p>Save notes and links, then ask questions across everything you saved.</p>
      </header>

      <main className="layout">
        <div className="column">
          <AddItemForm onAccepted={refresh} />
          <ItemList
            items={items}
            isLoading={isLoading}
            error={error}
            isPolling={isPolling}
          />
        </div>

        <div className="column">
          <AskPanel readyItemCount={readyItemCount} />
        </div>
      </main>
    </div>
  );
}
