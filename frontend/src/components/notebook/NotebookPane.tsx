"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useNotebookStore } from "@/stores/notebookStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useKernel } from "@/hooks/useKernel";
import NotebookCell from "./NotebookCell";
import ThinkingBlock from "./ThinkingBlock";

export default function NotebookPane() {
  const { cells, addCell, updateCellOutputs, pipelineRunning, currentPhase, latestThinking } = useNotebookStore();
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const { status, executeCell } = useKernel(activeSessionId ?? "");
  const [activeCellId, setActiveCellId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [cells.length]);

  const handleRunCell = useCallback(
    async (cellId: string, source: string) => {
      const outputs = await executeCell(cellId, source);
      updateCellOutputs(cellId, outputs);
    },
    [executeCell, updateCellOutputs]
  );

  const handleRunAll = useCallback(async () => {
    for (const cell of cells) {
      if (cell.cell_type === "code") {
        const outputs = await executeCell(cell.id, cell.source);
        updateCellOutputs(cell.id, outputs);
      }
    }
  }, [cells, executeCell, updateCellOutputs]);

  const statusColor =
    status === "connected"
      ? "bg-green-400"
      : status === "busy"
      ? "bg-yellow-400"
      : "bg-gray-400";

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-200 bg-white">
        <button
          onClick={handleRunAll}
          className="px-3 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors"
        >
          Run All
        </button>
        <button
          onClick={() => addCell(cells.length, "code")}
          className="px-3 py-1 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
        >
          + Code
        </button>
        <button
          onClick={() => addCell(cells.length, "markdown")}
          className="px-3 py-1 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
        >
          + Markdown
        </button>
        <div className="ml-auto flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${statusColor}`} />
          <span className="text-[10px] text-gray-400 capitalize">{status}</span>
        </div>
      </div>

      {/* Phase progress bar */}
      {pipelineRunning && currentPhase && (
        <div className="px-4 py-1.5 bg-blue-50 border-b border-blue-100">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-blue-700 font-medium">{currentPhase}</span>
          </div>
          <div className="mt-1 h-1 bg-blue-100 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{ width: "60%" }} />
          </div>
        </div>
      )}

      {/* Cell list */}
      <div className="flex-grow overflow-y-auto p-4">
        {cells.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 text-sm gap-2">
            <p>No cells yet</p>
            <button
              onClick={() => addCell(0, "code")}
              className="text-blue-500 hover:underline text-xs"
            >
              Add a code cell to get started
            </button>
          </div>
        ) : (
          <>
            {cells.map((cell) => (
              <NotebookCell
                key={cell.id}
                cell={cell}
                isActive={cell.id === activeCellId}
                onFocus={() => setActiveCellId(cell.id)}
                onRun={handleRunCell}
              />
            ))}
            {pipelineRunning && latestThinking && (
              <ThinkingBlock content={latestThinking} />
            )}
            <div ref={bottomRef} />
          </>
        )}
      </div>
    </div>
  );
}
