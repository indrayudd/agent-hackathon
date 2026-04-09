"use client";

import { useNotebookStore, type NotebookData } from "@/stores/notebookStore";

const statusIcon: Record<NotebookData["status"], string> = {
  idle: "",
  running: "\u23F3",
  complete: "\u2705",
  timeout: "\u23F1",
};

export default function NotebookTabs() {
  const notebooks = useNotebookStore((s: any) => s.notebooks) as Record<string, NotebookData>;
  const activeId = useNotebookStore((s: any) => s.activeNotebookId) as string;
  const setActive = useNotebookStore((s: any) => s.setActiveNotebook) as (id: string) => void;

  const tabs: NotebookData[] = Object.values(notebooks);
  // Don't render tabs if there's only the main notebook
  if (tabs.length <= 1) return null;

  return (
    <div className="flex gap-1 px-2 py-1 border-b border-outline-variant bg-surface-container-lowest overflow-x-auto">
      {tabs.map((nb) => {
        const isActive = nb.id === activeId;
        const icon = nb.id === "main" ? "\uD83D\uDCCB" : "\uD83D\uDD0D";
        const badge = statusIcon[nb.status];
        const label = nb.id === "main" ? "Main" : nb.title;
        return (
          <button
            key={nb.id}
            onClick={() => setActive(nb.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
              isActive
                ? "bg-primary/10 text-primary border border-primary/30"
                : "text-on-surface-variant hover:bg-surface-container-high"
            }`}
          >
            <span>{icon}</span>
            <span className="max-w-[160px] truncate">{label}</span>
            {badge && <span>{badge}</span>}
            {nb.id !== "main" && (
              <span className="text-xs text-on-surface-variant">
                ({nb.cells.length})
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
