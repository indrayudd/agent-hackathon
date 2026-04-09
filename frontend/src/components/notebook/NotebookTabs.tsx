"use client";

import { useNotebookStore, type NotebookData } from "@/stores/notebookStore";

export default function NotebookTabs() {
  const notebooks = useNotebookStore((s: any) => s.notebooks) as Record<string, NotebookData>;
  const activeId = useNotebookStore((s: any) => s.activeNotebookId) as string;
  const setActive = useNotebookStore((s: any) => s.setActiveNotebook) as (id: string) => void;

  const tabs: NotebookData[] = Object.values(notebooks);
  if (tabs.length <= 1) return null;

  return (
    <div className="flex items-center gap-1 px-3 py-1.5 border-b border-outline-variant/30 bg-surface-container-low shrink-0 min-h-[40px] overflow-x-auto">
      {tabs.map((nb) => {
        const isActive = nb.id === activeId;
        const isMain = nb.id === "main";
        return (
          <button
            key={nb.id}
            onClick={() => setActive(nb.id)}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium whitespace-nowrap transition-colors font-body ${
              isActive
                ? "bg-primary/10 text-primary"
                : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
            }`}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              {isMain ? "description" : "science"}
            </span>
            <span className="max-w-[180px] truncate">
              {isMain ? "Main" : nb.title}
            </span>
            {!isMain && nb.status !== "idle" && (
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "14px" }}
              >
                {nb.status === "running"
                  ? "schedule"
                  : nb.status === "complete"
                  ? "check_circle"
                  : "timer_off"}
              </span>
            )}
            {!isMain && (
              <span className="text-[10px] text-on-surface-variant">
                ({nb.cells.length})
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
