"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useNotebookStore } from "@/stores/notebookStore";
import type { ActivityLogEntry } from "@/stores/notebookStore";
import {
  summarizeCellSource,
  ACTIVITY_CONFIG,
  HypothesisIcon,
  MarkdownIcon,
  CodeIcon,
} from "./activityUtils";

/* ── Helpers ────────────────────────────────────────────── */

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function scrollToCell(cellId: string) {
  // Switch to notebook tab if not already there
  const store = useNotebookStore.getState();
  if (store.activeTab !== "notebook") {
    store.setActiveTab("notebook");
    // Wait for React to render the notebook pane before scrolling
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        doScroll(cellId);
      });
    });
  } else {
    doScroll(cellId);
  }
}

function doScroll(cellId: string) {
  const el = document.getElementById(`cell-${cellId}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("ring-2", "ring-blue-400", "ring-offset-2");
    setTimeout(() => el.classList.remove("ring-2", "ring-blue-400", "ring-offset-2"), 1500);
  }
}

function isInvestigationHeader(entry: ActivityLogEntry): boolean {
  return !!(entry.hypothesisId && entry.activity === "thinking" && /^Hypothesis \d+/.test(entry.detail));
}

function isCellNode(entry: ActivityLogEntry): boolean {
  return entry.activity === "generating" && !!entry.cellId;
}

/* ── Entry components ───────────────────────────────────── */

function InvestigationHeader({ entry }: { entry: ActivityLogEntry }) {
  return (
    <div className="flex items-start gap-2 mt-3 mb-1">
      {/* Dot */}
      <div className="relative flex-shrink-0 flex items-center justify-center w-5 h-5 rounded-full bg-purple-100 ring-2 ring-purple-200">
        <HypothesisIcon className="w-3 h-3 text-purple-600" />
      </div>
      <p className="text-xs font-semibold text-purple-700 leading-5">{entry.detail}</p>
    </div>
  );
}

function CellCard({
  entry,
  isLast,
}: {
  entry: ActivityLogEntry;
  isLast: boolean;
}) {
  const isHypothesis = !!entry.hypothesisId;
  const dotColor = isHypothesis ? "bg-purple-500" : "bg-blue-500";
  const borderColor = isHypothesis
    ? "border-purple-200 hover:border-purple-300"
    : "border-gray-200 hover:border-blue-300";
  const lineColor = isHypothesis ? "bg-purple-200" : "bg-gray-200";
  const CellIcon = entry.cellType === "markdown" ? MarkdownIcon : CodeIcon;
  const iconColor = isHypothesis ? "text-purple-500" : "text-blue-500";

  const summary = summarizeCellSource(entry.detail, entry.cellType);

  return (
    <div className="flex items-stretch gap-0 relative">
      {/* Timeline rail */}
      <div className="flex flex-col items-center w-5 flex-shrink-0">
        <div className={`w-0.5 flex-grow ${lineColor}`} />
        <div
          className={`w-3 h-3 rounded-full ${dotColor} flex-shrink-0 ${isLast ? "ring-2 ring-offset-1 " + (isHypothesis ? "ring-purple-300" : "ring-blue-300") : ""}`}
        />
        <div className={`w-0.5 flex-grow ${lineColor}`} />
      </div>

      {/* Card */}
      <button
        onClick={() => entry.cellId && scrollToCell(entry.cellId)}
        className={`flex-1 ml-1.5 my-0.5 p-1.5 rounded border ${borderColor} bg-white text-left transition-colors cursor-pointer`}
      >
        <div className="flex items-center gap-1.5">
          <CellIcon className={`w-3.5 h-3.5 flex-shrink-0 ${iconColor}`} />
          <span className="text-[11px] text-gray-800 font-medium truncate">{summary}</span>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[9px] text-gray-400">{formatTime(entry.ts)}</span>
          {entry.phase && (
            <span className="text-[9px] text-gray-400 truncate">{entry.phase}</span>
          )}
        </div>
      </button>
    </div>
  );
}

function IntermediateEntry({
  entry,
  isLast,
}: {
  entry: ActivityLogEntry;
  isLast: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const cfg = ACTIVITY_CONFIG[entry.activity];
  const Icon = cfg.Icon;
  const isHypothesis = !!entry.hypothesisId;
  const lineStyle = isHypothesis ? "border-purple-200" : "border-gray-200";

  const isLong = entry.detail.length > 50;
  const truncated = isLong ? entry.detail.slice(0, 50) : entry.detail;

  return (
    <div className="flex items-start gap-0 relative">
      {/* Timeline rail (dashed) */}
      <div className="flex flex-col items-center w-5 flex-shrink-0">
        <div className={`w-0 flex-grow border-l border-dashed ${lineStyle}`} />
        <div
          className={`w-2 h-2 rounded-full ${cfg.dotColor} flex-shrink-0 ${isLast ? "ring-1 " + cfg.ringColor : ""}`}
        />
        <div className={`w-0 flex-grow border-l border-dashed ${lineStyle}`} />
      </div>

      {/* Content */}
      <div className="flex-1 ml-1.5 py-0.5">
        <div className="flex items-center gap-1">
          <Icon className={`w-3 h-3 flex-shrink-0 ${cfg.color}`} />
          <span className="text-[10px] text-gray-500">
            {expanded ? entry.detail : truncated}
            {isLong && !expanded && (
              <button
                onClick={() => setExpanded(true)}
                className="text-blue-500 hover:text-blue-700 hover:underline ml-0.5"
              >
                &hellip;
              </button>
            )}
            {isLong && expanded && (
              <button
                onClick={() => setExpanded(false)}
                className="text-blue-500 hover:text-blue-700 hover:underline ml-0.5"
              >
                less
              </button>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}

function ChatActionCard({ entry, isLast }: { entry: ActivityLogEntry; isLast: boolean }) {
  const actionLabel =
    entry.chatAction === "edit_cell" ? "Edited" :
    entry.chatAction === "delete_cells" ? "Deleted" :
    entry.chatAction === "reorder_cell" ? "Reordered" :
    entry.chatAction === "new_cell" ? "Created" : "Action";

  return (
    <div className="flex items-stretch gap-0 relative">
      {/* Timeline rail */}
      <div className="flex flex-col items-center w-5 flex-shrink-0">
        <div className="w-0.5 flex-grow bg-indigo-200" />
        <div
          className={`w-3 h-3 rounded-full bg-indigo-500 flex-shrink-0 ${isLast ? "ring-2 ring-offset-1 ring-indigo-300" : ""}`}
        />
        <div className="w-0.5 flex-grow bg-indigo-200" />
      </div>

      {/* Card */}
      <div className="flex-1 ml-1.5 my-0.5 p-1.5 rounded border border-indigo-200 bg-indigo-50 text-left">
        <div className="flex items-center gap-1.5">
          <svg className="w-3.5 h-3.5 flex-shrink-0 text-indigo-500" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 2a6 6 0 1 0 0 12A6 6 0 0 0 8 2Z" />
            <path d="M8 5v3l2 1" />
          </svg>
          <span className="text-[10px] font-semibold text-indigo-700">{actionLabel}</span>
        </div>
        <p className="text-[10px] text-indigo-600 mt-0.5 truncate">{entry.detail}</p>
        <span className="text-[9px] text-indigo-400">{formatTime(entry.ts)}</span>
      </div>
    </div>
  );
}

function CompletionBanner({ entry }: { entry: ActivityLogEntry }) {
  return (
    <div className="mt-3 mb-1">
      {/* End-of-timeline cap */}
      <div className="flex items-center gap-0">
        <div className="flex flex-col items-center w-5 flex-shrink-0">
          <div className="w-0.5 h-3 bg-green-200" />
          <div className="w-3.5 h-3.5 rounded-full bg-green-500 ring-4 ring-green-100 flex-shrink-0" />
        </div>
        <div className="flex-1 ml-1.5" />
      </div>

      {/* Banner */}
      <div className="ml-0 mt-2 rounded-lg bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center flex-shrink-0">
            <svg className="w-3.5 h-3.5 text-white" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3.5,8 6.5,11 12.5,5" />
            </svg>
          </div>
          <div>
            <p className="text-xs font-semibold text-green-800">{entry.detail}</p>
            <p className="text-[9px] text-green-600 mt-0.5">{formatTime(entry.ts)}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Main component ─────────────────────────────────────── */

export default function AgentActivityBadge() {
  const activityLog = useNotebookStore((s) => s.activityLog);
  const pipelineRunning = useNotebookStore((s) => s.pipelineRunning);
  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);

  // Track if user is scrolled to bottom
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    atBottom.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
  }, []);

  // Auto-scroll on new entries (only if at bottom)
  useEffect(() => {
    if (atBottom.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activityLog.length]);

  if (activityLog.length === 0 && !pipelineRunning) return null;

  return (
    <div className="mt-4">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <h3 className="text-xs font-semibold text-gray-700">Agent Activity</h3>
        {pipelineRunning && (
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
          </span>
        )}
        <span className="text-[9px] text-gray-400 ml-auto">{activityLog.length}</span>
      </div>

      {/* Timeline */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="max-h-[calc(100vh-400px)] overflow-y-auto pr-1"
      >
        {activityLog.map((entry, i) => {
          const isLast = i === activityLog.length - 1;

          if (isInvestigationHeader(entry)) {
            return <InvestigationHeader key={entry.id} entry={entry} />;
          }

          if (entry.activity === "complete") {
            return <CompletionBanner key={entry.id} entry={entry} />;
          }

          if (entry.chatAction) {
            return <ChatActionCard key={entry.id} entry={entry} isLast={isLast} />;
          }

          if (isCellNode(entry)) {
            return <CellCard key={entry.id} entry={entry} isLast={isLast} />;
          }

          return (
            <IntermediateEntry key={entry.id} entry={entry} isLast={isLast} />
          );
        })}
      </div>
    </div>
  );
}
