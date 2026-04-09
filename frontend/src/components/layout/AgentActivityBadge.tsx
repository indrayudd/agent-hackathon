"use client";

import { useState } from "react";
import { useNotebookStore } from "@/stores/notebookStore";
import type { ActivityLogEntry } from "@/stores/notebookStore";
import {
  summarizeCellSource,
  ACTIVITY_CONFIG,
  getActivityDetail,
  getActivityLabel,
  isNarrationUpdate,
  HypothesisIcon,
  MarkdownIcon,
  CodeIcon,
  CheckIcon,
} from "./activityUtils";

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function scrollToCell(cellId: string) {
  const store = useNotebookStore.getState();
  if (store.activeTab !== "notebook") {
    store.setActiveTab("notebook");
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
    el.classList.add("ring-2", "ring-primary/40", "ring-offset-2", "activity-highlight");
    setTimeout(() => el.classList.remove("ring-2", "ring-primary/40", "ring-offset-2", "activity-highlight"), 1500);
  }
}

function isInvestigationHeader(entry: ActivityLogEntry): boolean {
  return !!(entry.hypothesisId && entry.activity === "thinking" && /^Hypothesis \d+/.test(entry.detail));
}

function isCellNode(entry: ActivityLogEntry): boolean {
  return entry.activity === "generating" && !!entry.cellId;
}

function isSynthesisEntry(entry: ActivityLogEntry): boolean {
  return (
    (entry.activity === "thinking" && isNarrationUpdate(entry.detail)) ||
    (entry.activity === "generating" && !entry.cellId && isNarrationUpdate(entry.detail))
  );
}

function isRecoveryEntry(entry: ActivityLogEntry): boolean {
  return entry.activity === "fixing" || entry.activity === "backtracking";
}

function formatRelativePhase(phase: string): string {
  return phase ? phase.replace(/^Chat Investigation:\s*/i, "") : "";
}

function renderGlyph(glyph: string, className: string) {
  return (
    <span className={`material-symbols-outlined ${className}`} style={{ fontVariationSettings: '"FILL" 1' }}>
      {glyph}
    </span>
  );
}

function InvestigationHeader({ entry, index }: { entry: ActivityLogEntry; index: number }) {
  return (
    <div
      className="flex items-start gap-2 mt-3 mb-1 animate-activity-in"
      style={{ animationDelay: `${index * 18}ms` }}
    >
      <div className="relative flex-shrink-0 flex items-center justify-center w-6 h-6 rounded-full bg-primary-fixed ring-2 ring-primary-fixed-dim shadow-sm">
        <HypothesisIcon className="w-3.5 h-3.5 text-on-primary-fixed-variant" />
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-[0.24em] text-on-surface-variant">Investigation</p>
        <p className="text-xs font-semibold text-primary leading-5">{entry.detail}</p>
      </div>
    </div>
  );
}

function CellCard({
  entry,
  isLast,
  index,
}: {
  entry: ActivityLogEntry;
  isLast: boolean;
  index: number;
}) {
  const cellType = entry.cellType ?? "code";
  const summary = summarizeCellSource(entry.detail, cellType);
  const CellIcon = cellType === "markdown" ? MarkdownIcon : CodeIcon;
  const cfg = ACTIVITY_CONFIG[entry.activity];

  return (
    <div className="flex items-stretch gap-0 relative animate-activity-in" style={{ animationDelay: `${index * 18}ms` }}>
      <div className="flex flex-col items-center w-5 flex-shrink-0">
        <div className="w-0.5 flex-grow bg-outline-variant/30" />
        <div
          className={`w-3 h-3 rounded-full ${cfg.dotColor} flex-shrink-0 shadow-sm ${isLast ? "ring-2 ring-offset-1 ring-primary/30" : ""}`}
        />
        <div className="w-0.5 flex-grow bg-outline-variant/30" />
      </div>
      <button
        onClick={() => entry.cellId && scrollToCell(entry.cellId)}
        className={`flex-1 ml-1.5 my-0.5 rounded-2xl border text-left shadow-sm transition-all duration-200 cursor-pointer hover:-translate-y-0.5 hover:shadow-md ${cfg.cardClass}`}
      >
        <div className="flex items-start gap-3 p-3">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-blue-50 text-primary shadow-inner">
            <CellIcon className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-on-surface-variant">Notebook cell</span>
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-primary">
                {cellType}
              </span>
            </div>
            <p className="mt-1 text-sm font-semibold text-on-surface truncate">{summary}</p>
            <p className="mt-1 text-[10px] text-on-surface-variant">
              {formatTime(entry.ts)}
              {entry.phase ? ` · ${entry.phase}` : ""}
            </p>
          </div>
        </div>
      </button>
    </div>
  );
}

function IntermediateEntry({
  entry,
  isLast,
  index,
}: {
  entry: ActivityLogEntry;
  isLast: boolean;
  index: number;
}) {
  const cfg = ACTIVITY_CONFIG[entry.activity];
  const Icon = cfg.Icon;
  const title = getActivityLabel(entry);
  const detail = getActivityDetail(entry);
  const recovery = isRecoveryEntry(entry);
  const synthesis = isSynthesisEntry(entry);
  const isComplete = entry.activity === "complete";
  const glyph = entry.activity === "fixing" && /error/i.test(entry.detail)
    ? "error"
    : entry.activity === "backtracking"
      ? "replay"
      : synthesis
        ? "summarize"
        : cfg.glyph;

  const cardClasses = synthesis
    ? "border-violet-200/90 bg-gradient-to-br from-violet-50 via-white to-sky-50"
    : recovery
      ? "border-rose-200/90 bg-gradient-to-br from-rose-50 via-white to-orange-50"
      : isComplete
        ? "border-emerald-200/90 bg-gradient-to-br from-emerald-50 via-white to-green-50"
        : "border-outline-variant/20 bg-white/95";

  return (
    <div
      className="flex items-start gap-0 relative animate-activity-in"
      style={{ animationDelay: `${index * 18}ms` }}
    >
      <div className="flex flex-col items-center w-5 flex-shrink-0">
        <div className="w-0 flex-grow border-l border-dashed border-outline-variant/30" />
        <div
          className={`w-2.5 h-2.5 rounded-full ${cfg.dotColor} flex-shrink-0 shadow-sm ${isLast ? "ring-1 " + cfg.ringColor : ""}`}
        />
        <div className="w-0 flex-grow border-l border-dashed border-outline-variant/30" />
      </div>
      <div className="flex-1 ml-1.5">
        <div className={`overflow-hidden rounded-2xl border shadow-sm transition-all duration-200 ${cardClasses} ${recovery ? "ring-1 ring-rose-200/60" : ""}`}>
          <div className={`h-1.5 bg-gradient-to-r ${cfg.accentClass} ${synthesis ? "animate-activity-sheen" : ""}`} />
          <div className="flex items-start gap-3 p-3">
            <div className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl ${synthesis ? "bg-violet-100 text-violet-700" : recovery ? "bg-rose-100 text-rose-700" : isComplete ? "bg-emerald-100 text-emerald-700" : "bg-surface-container-high text-primary"} shadow-inner`}>
              {glyph ? (
                renderGlyph(glyph, "text-[18px]")
              ) : (
                <Icon className={`w-4 h-4 flex-shrink-0 ${cfg.color}`} />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-semibold uppercase tracking-[0.24em] ${recovery ? "text-rose-700" : synthesis ? "text-violet-700" : isComplete ? "text-emerald-700" : "text-on-surface-variant"}`}>
                  {title}
                </span>
                {entry.phase && (
                  <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.18em] ${recovery ? "bg-rose-100 text-rose-700" : synthesis ? "bg-violet-100 text-violet-700" : "bg-surface-container-low text-on-surface-variant"}`}>
                    {formatRelativePhase(entry.phase)}
                  </span>
                )}
              </div>
              <p className={`mt-1 text-sm leading-5 ${recovery ? "text-rose-900" : synthesis ? "text-violet-950" : isComplete ? "text-emerald-950" : "text-on-surface-variant"}`}>
                {detail}
              </p>
              {synthesis && (
                <div className="mt-2 flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-violet-500 animate-pulse" />
                  <span className="h-1.5 w-1.5 rounded-full bg-sky-500 animate-pulse [animation-delay:120ms]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-indigo-500 animate-pulse [animation-delay:240ms]" />
                  <span className="text-[10px] text-on-surface-variant">Assembling the narrative</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChatActionCard({ entry, isLast, index }: { entry: ActivityLogEntry; isLast: boolean; index: number }) {
  const actionLabel =
    entry.chatAction === "edit_cell" ? "Edited" :
    entry.chatAction === "delete_cells" ? "Deleted" :
    entry.chatAction === "reorder_cell" ? "Reordered" :
    entry.chatAction === "new_cell" ? "Created" : "Action";

  return (
    <div className="flex items-stretch gap-0 relative animate-activity-in" style={{ animationDelay: `${index * 18}ms` }}>
      <div className="flex flex-col items-center w-5 flex-shrink-0">
        <div className="w-0.5 flex-grow bg-secondary-fixed-dim/40" />
        <div
          className={`w-3 h-3 rounded-full bg-secondary flex-shrink-0 ${isLast ? "ring-2 ring-offset-1 ring-secondary-container" : ""}`}
        />
        <div className="w-0.5 flex-grow bg-secondary-fixed-dim/40" />
      </div>
      <div className="flex-1 ml-1.5 my-0.5 p-3 rounded-2xl border border-secondary-fixed-dim/30 bg-gradient-to-br from-secondary-fixed/50 to-white text-left shadow-sm">
        <div className="flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[14px] text-secondary">edit_note</span>
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-on-secondary-container">{actionLabel}</span>
        </div>
        <p className="text-[10px] text-secondary mt-1 truncate">{entry.detail}</p>
        <span className="text-[9px] text-on-surface-variant mt-1 inline-block">{formatTime(entry.ts)}</span>
      </div>
    </div>
  );
}

function CompletionBanner({ entry, index }: { entry: ActivityLogEntry; index: number }) {
  return (
    <div
      className="mt-2 mb-1 overflow-hidden rounded-2xl border border-emerald-200/90 bg-gradient-to-r from-emerald-50 via-white to-green-50 px-4 py-3 shadow-sm animate-activity-in"
      style={{ animationDelay: `${index * 18}ms` }}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 shadow-inner">
          <CheckIcon className="w-5 h-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-emerald-700">
            Analysis complete
          </p>
          <p className="mt-1 text-sm text-emerald-950 leading-5">{entry.detail}</p>
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl border border-dashed border-outline-variant/30 bg-surface-container-low/60 px-4 py-5 text-center">
      <p className="text-sm font-semibold text-on-surface">Agent activity will appear here</p>
      <p className="mt-1 text-xs text-on-surface-variant">Fixes, cell runs, and narrative synthesis are summarized as they happen.</p>
    </div>
  );
}

export default function AgentActivityBadge() {
  const log = useNotebookStore((s) => s.activityLog);
  const activeNotebookId = useNotebookStore((s) => s.activeNotebookId);
  const [expanded, setExpanded] = useState(false);

  // Filter entries by active notebook tab
  const filteredLog = log.filter((entry) => {
    if (activeNotebookId === "main") {
      // Main tab: show orchestrator events (main or untagged)
      return !entry.notebookId || entry.notebookId === "main";
    }
    // Agent tab: show entries for this specific notebook
    return entry.notebookId === activeNotebookId;
  });

  if (filteredLog.length === 0) {
    return (
      <div className="mt-4">
        <EmptyState />
      </div>
    );
  }

  const entries = filteredLog.filter((entry) => entry.detail.trim().length > 0);
  const condensedEntries = entries.slice(-6);

  const renderEntry = (entry: ActivityLogEntry, index: number, total: number) => {
    const isLast = index === total - 1;

    if (isInvestigationHeader(entry)) {
      return <InvestigationHeader key={entry.id} entry={entry} index={index} />;
    }

    if (entry.activity === "complete") {
      return <CompletionBanner key={entry.id} entry={entry} index={index} />;
    }

    if (entry.chatAction) {
      return <ChatActionCard key={entry.id} entry={entry} isLast={isLast} index={index} />;
    }

    if (isCellNode(entry)) {
      return <CellCard key={entry.id} entry={entry} isLast={isLast} index={index} />;
    }

    return (
      <IntermediateEntry
        key={entry.id}
        entry={entry}
        isLast={isLast}
        index={index}
      />
    );
  };

  return (
    <div className="mt-4">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <span className="material-symbols-outlined text-[16px] text-primary" style={{ fontVariationSettings: '"FILL" 1' }}>bolt</span>
        <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-on-surface">Agent Actions</p>
      </div>

      {/* Timeline entries */}
      <div className="divide-y divide-outline-variant/15">
        {condensedEntries.map((entry) => {
          const cfg = ACTIVITY_CONFIG[entry.activity];
          const label = getActivityLabel(entry);
          const detail = getActivityDetail(entry);
          const glyph = entry.activity === "fixing" ? "build" : entry.activity === "backtracking" ? "replay" : entry.activity === "complete" ? "check_circle" : cfg.glyph || "code";
          return (
            <button
              key={entry.id}
              type="button"
              onClick={() => entry.cellId ? scrollToCell(entry.cellId) : setExpanded(true)}
              className="flex w-full flex-col gap-1 py-3 text-left transition-colors hover:bg-surface-container-low/50"
            >
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 shrink-0 rounded-full ${cfg.dotColor}`} />
                <span className="flex-1 truncate text-xs font-semibold text-on-surface">{label}</span>
                <span className="shrink-0 text-[10px] tabular-nums text-on-surface-variant">{formatTime(entry.ts)}</span>
              </div>
              <div className="ml-4 flex items-start gap-1.5 text-[11px] leading-4 text-on-surface-variant">
                <span className="material-symbols-outlined text-[13px] mt-0.5 shrink-0">{glyph}</span>
                <span className="line-clamp-2">{detail}</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* View full timeline button */}
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-outline-variant/20 bg-surface py-2.5 text-[10px] font-bold uppercase tracking-[0.22em] text-on-surface-variant transition-colors hover:bg-surface-container"
      >
        View full timeline
        <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
      </button>

      {expanded && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/45 px-4">
          <div className="flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-[1.75rem] border border-outline-variant/20 bg-surface shadow-2xl">
            <div className="flex items-center justify-between border-b border-outline-variant/20 px-5 py-4">
              <div>
                <p className="text-sm font-semibold text-on-surface">Agent Timeline</p>
                <p className="text-xs text-on-surface-variant">Full execution log</p>
              </div>
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="rounded-full border border-outline-variant/20 px-3 py-1 text-xs font-semibold text-on-surface-variant transition-colors hover:bg-surface-container"
              >
                Close
              </button>
            </div>
            <div className="overflow-y-auto px-5 py-4">
              <div className="space-y-1.5">
                {(() => {
                  const allEntries = log.filter((e) => e.detail.trim().length > 0);
                  // Group by notebookId for section headers
                  const groups: { notebookId: string; entries: ActivityLogEntry[] }[] = [];
                  let currentGroup: string | null = null;
                  for (const entry of allEntries) {
                    const nbId = entry.notebookId || "main";
                    if (nbId !== currentGroup) {
                      currentGroup = nbId;
                      groups.push({ notebookId: nbId, entries: [entry] });
                    } else {
                      groups[groups.length - 1].entries.push(entry);
                    }
                  }
                  let globalIdx = 0;
                  return groups.map((group) => (
                    <div key={`${group.notebookId}-${group.entries[0]?.id}`}>
                      {group.notebookId !== "main" && (
                        <div className="mt-3 mb-1 px-1">
                          <span className="text-[10px] font-bold uppercase tracking-[0.24em] text-primary/70">{group.notebookId}</span>
                        </div>
                      )}
                      {group.entries.map((entry) => {
                        const idx = globalIdx++;
                        return renderEntry(entry, idx, allEntries.length);
                      })}
                    </div>
                  ));
                })()}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
