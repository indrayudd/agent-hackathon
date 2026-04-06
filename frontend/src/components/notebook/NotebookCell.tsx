"use client";

import { useState, useCallback } from "react";
import type { Cell } from "@/lib/types";
import { useNotebookStore } from "@/stores/notebookStore";
import CellToolbar from "./CellToolbar";
import CodeEditor from "./CodeEditor";
import CellOutput from "./CellOutput";
import ThinkingBlock from "./ThinkingBlock";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  cell: Cell;
  isActive: boolean;
  onFocus: () => void;
  onRun: (cellId: string, source: string) => void;
}

export default function NotebookCell({ cell, isActive, onFocus, onRun }: Props) {
  const { updateCellSource, deleteCell, moveCell } = useNotebookStore();
  const [editingMarkdown, setEditingMarkdown] = useState(false);

  const handleRun = useCallback(() => {
    onRun(cell.id, cell.source);
  }, [cell.id, cell.source, onRun]);

  const hasOutput = cell.outputs.length > 0 || cell.execution_count !== null;
  const execLabel = cell.executing
    ? "[*]:"
    : cell.execution_count !== null
    ? `[${cell.execution_count}]:`
    : "[ ]:";

  const borderClass = cell.cell_type === "markdown"
    ? "border-transparent border-l-0"
    : cell.error
    ? "border-red-400 border-l-4 border-l-red-500"
    : cell.executing
    ? "border-blue-400 border-l-4 border-l-blue-500 animate-pulse"
    : hasOutput
    ? "border-green-400 border-l-4 border-l-green-500"
    : "border-gray-200 border-l-4 border-l-gray-300 hover:border-gray-300";

  const execLabelClass = cell.executing
    ? "text-xs text-blue-500 font-mono animate-pulse"
    : hasOutput
    ? "text-xs text-green-600 font-mono"
    : "text-xs text-gray-400 font-mono";

  return (
    <>
      {cell.thinking && <ThinkingBlock content={cell.thinking} />}
      <div
        id={`cell-${cell.id}`}
        className={`group relative flex border rounded mb-2 transition-colors ${borderClass}`}
        onClick={onFocus}
      >
        {/* Executing spinner overlay */}
        {cell.executing && (
          <div className="absolute top-2 right-2 z-10">
            <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      {/* Execution count gutter (code cells only) */}
      {cell.cell_type === "code" && (
        <div className="flex-shrink-0 w-14 pt-8 text-right pr-2 select-none">
          <span className={execLabelClass}>{execLabel}</span>
        </div>
      )}

      {/* Cell body */}
      <div className="flex-grow min-w-0">
        {/* Toolbar: visible on hover or when active */}
        <div className={`${isActive ? "opacity-100" : "opacity-0 group-hover:opacity-100"} transition-opacity`}>
          <CellToolbar
            cellType={cell.cell_type}
            onRun={handleRun}
            onDelete={() => deleteCell(cell.id)}
            onMoveUp={() => moveCell(cell.id, "up")}
            onMoveDown={() => moveCell(cell.id, "down")}
          />
        </div>

        {/* Editor / content area */}
        {cell.cell_type === "code" ? (
          <>
            <CodeEditor
              cellId={cell.id}
              value={cell.source}
              onChange={updateCellSource}
              onRun={handleRun}
            />
            <CellOutput outputs={cell.outputs} />
          </>
        ) : (
          /* Markdown cell */
          <div className="px-3 py-2">
            {editingMarkdown ? (
              <textarea
                className="w-full min-h-[60px] p-2 text-sm font-mono border border-gray-200 rounded resize-y focus:outline-none focus:ring-1 focus:ring-blue-400"
                value={cell.source}
                onChange={(e) => updateCellSource(cell.id, e.target.value)}
                onBlur={() => setEditingMarkdown(false)}
                autoFocus
              />
            ) : (
              <div
                className="prose prose-sm max-w-none cursor-text min-h-[40px] prose-h1:text-xl prose-h1:font-bold prose-h1:border-b prose-h1:border-gray-200 prose-h1:pb-2 prose-h2:text-lg prose-h2:font-semibold prose-h3:text-base prose-h3:font-semibold prose-hr:my-4 prose-hr:border-gray-300 prose-blockquote:border-l-blue-400 prose-blockquote:bg-blue-50 prose-blockquote:py-1 prose-blockquote:px-3 prose-blockquote:rounded-r prose-table:text-xs"
                onDoubleClick={() => setEditingMarkdown(true)}
              >
                {cell.source ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {cell.source.replace(/\\n/g, "\n")}
                  </ReactMarkdown>
                ) : (
                  <p className="text-gray-400 italic">Double-click to edit markdown</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
      </div>
    </>
  );
}
