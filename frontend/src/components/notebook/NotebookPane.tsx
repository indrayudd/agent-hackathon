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
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const autoFollowRef = useRef(true);
  const rafRef = useRef<number | null>(null);
  const scrollIdleTimerRef = useRef<number | null>(null);
  const programmaticScrollRef = useRef(false);
  const manualScrollIntentRef = useRef(false);
  const manualIntentTimerRef = useRef<number | null>(null);

  const getDistanceFromBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return Number.POSITIVE_INFINITY;
    return el.scrollHeight - el.scrollTop - el.clientHeight;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const el = scrollContainerRef.current;
    if (!el) return;
    programmaticScrollRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior });
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        programmaticScrollRef.current = false;
      });
    });
  }, []);

  const markManualScrollIntent = useCallback(() => {
    manualScrollIntentRef.current = true;
    if (manualIntentTimerRef.current !== null) {
      window.clearTimeout(manualIntentTimerRef.current);
    }
    manualIntentTimerRef.current = window.setTimeout(() => {
      manualScrollIntentRef.current = false;
      manualIntentTimerRef.current = null;
    }, 220);
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    if (programmaticScrollRef.current) return;

    const distanceFromBottom = getDistanceFromBottom();
    const releaseThreshold = 200;
    const resumeThreshold = 96;

    if (manualScrollIntentRef.current && distanceFromBottom > releaseThreshold) {
      autoFollowRef.current = false;
    } else if (distanceFromBottom <= resumeThreshold) {
      autoFollowRef.current = true;
    }

    if (scrollIdleTimerRef.current !== null) {
      window.clearTimeout(scrollIdleTimerRef.current);
    }

    scrollIdleTimerRef.current = window.setTimeout(() => {
      const settledDistance = getDistanceFromBottom();
      if (settledDistance <= 320 && pipelineRunning) {
        autoFollowRef.current = true;
        scrollToBottom("auto");
      }
    }, 180);
  }, [getDistanceFromBottom, pipelineRunning, scrollToBottom]);

  useEffect(() => {
    if (!pipelineRunning || !autoFollowRef.current) return;

    let firstFrame: number | null = null;
    let secondFrame: number | null = null;

    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
    }

    firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => {
        scrollToBottom("auto");
        rafRef.current = null;
      });
    });
    rafRef.current = firstFrame;

    return () => {
      if (firstFrame !== null) {
        cancelAnimationFrame(firstFrame);
      }
      if (secondFrame !== null) {
        cancelAnimationFrame(secondFrame);
      }
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      if (scrollIdleTimerRef.current !== null) {
        window.clearTimeout(scrollIdleTimerRef.current);
        scrollIdleTimerRef.current = null;
      }
      if (manualIntentTimerRef.current !== null) {
        window.clearTimeout(manualIntentTimerRef.current);
        manualIntentTimerRef.current = null;
      }
    };
  }, [cells.length, latestThinking, currentPhase, pipelineRunning, scrollToBottom]);

  useEffect(() => {
    const el = contentRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(() => {
      if (autoFollowRef.current && pipelineRunning) {
        scrollToBottom("auto");
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, [scrollToBottom, pipelineRunning]);

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
      : "bg-outline";

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-surface to-surface-container-lowest">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-outline-variant/20 bg-surface/95 backdrop-blur-sm">
        <button
          onClick={handleRunAll}
          className="px-3 py-1 text-xs font-body font-medium rounded-lg bg-primary text-on-primary hover:opacity-90 transition-all shadow-sm"
        >
          Run All
        </button>
        <button
          onClick={() => addCell(cells.length, "code")}
          className="px-3 py-1 text-xs font-body rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container transition-colors"
        >
          + Code
        </button>
        <button
          onClick={() => addCell(cells.length, "markdown")}
          className="px-3 py-1 text-xs font-body rounded-lg border border-outline-variant text-on-surface-variant hover:bg-surface-container transition-colors"
        >
          + Markdown
        </button>
        <div className="ml-auto flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${statusColor}`} />
          <span className="text-[10px] text-on-surface-variant font-body capitalize">{status}</span>
        </div>
      </div>

      {/* Phase progress bar */}
      {pipelineRunning && currentPhase && (
        <div className="px-4 py-1.5 bg-primary/5 border-b border-primary/10">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-primary font-body font-medium">{currentPhase}</span>
          </div>
          <div className="mt-1 h-1 bg-primary/10 rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-primary to-primary-container rounded-full animate-pulse" style={{ width: "60%" }} />
          </div>
        </div>
      )}

      {/* Cell list */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        onWheel={markManualScrollIntent}
        onTouchMove={markManualScrollIntent}
        data-notebook-scroll
        className="flex-grow overflow-y-auto bg-surface-container-lowest px-8 py-12 notebook-scroll"
        style={{ scrollPaddingBottom: "8rem", overflowAnchor: "none" }}
      >
        <div ref={contentRef} className="max-w-4xl mx-auto relative">
          <div className="pointer-events-none absolute inset-x-0 -top-6 h-24 bg-gradient-to-b from-primary/5 via-transparent to-transparent" />
          {cells.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-on-surface-variant text-sm font-body gap-2">
              <p>No cells yet</p>
              <button
                onClick={() => addCell(0, "code")}
                className="text-primary hover:underline text-xs font-body"
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
            </>
          )}
        </div>
        <div className="h-32" />
      </div>
    </div>
  );
}
