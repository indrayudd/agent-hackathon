import { create } from "zustand";
import type { Cell } from "@/lib/types";
import { v4 as uuidv4 } from "uuid";

export type AgentActivity = "idle" | "thinking" | "generating" | "executing" | "fixing" | "backtracking" | "complete";

export interface ActivityLogEntry {
  id: number;
  activity: AgentActivity;
  detail: string;
  phase: string;
  ts: number;
  cellId?: string;
  cellType?: "code" | "markdown";
  hypothesisId?: string;
  chatAction?: string; // "new_cell" | "edit_cell" | "delete_cells" | "reorder_cell"
}

interface NotebookState {
  cells: Cell[];
  dirty: boolean;
  pipelineRunning: boolean;
  currentPhase: string;
  executionCounter: number;
  agentActivity: AgentActivity;
  agentActivityDetail: string;
  activityLog: ActivityLogEntry[];
  setCells: (cells: Cell[]) => void;
  addCell: (index: number, type: "code" | "markdown") => void;
  appendCell: (cell: Cell) => void;
  updateCellSource: (id: string, source: string) => void;
  updateCellOutputs: (id: string, outputs: Cell["outputs"]) => void;
  deleteCell: (id: string) => void;
  moveCell: (id: string, direction: "up" | "down") => void;
  setDirty: (dirty: boolean) => void;
  setPipelineRunning: (running: boolean) => void;
  setCurrentPhase: (phase: string) => void;
  setCellExecuting: (id: string, executing: boolean) => void;
  setCellError: (id: string, error: string | null) => void;
  setCellThinking: (id: string, thinking: string | null) => void;
  latestThinking: string;
  setLatestThinking: (text: string) => void;
  hypothesisGroups: { id: string; title: string; cellIds: string[] }[];
  addHypothesisGroup: (id: string, title: string) => void;
  setAgentActivity: (activity: AgentActivity, detail: string, extra?: Partial<Pick<ActivityLogEntry, "cellId" | "cellType" | "hypothesisId">>) => void;
  addChatAction: (detail: string, actionType: string) => void;
  clearActivityLog: () => void;
  resetForNewSession: () => void;
  activeTab: "notebook" | "story";
  setActiveTab: (tab: "notebook" | "story") => void;
}

export const useNotebookStore = create<NotebookState>((set) => ({
  cells: [],
  dirty: false,
  pipelineRunning: false,
  currentPhase: "",
  executionCounter: 0,
  latestThinking: "",
  agentActivity: "idle" as AgentActivity,
  agentActivityDetail: "",
  activityLog: [],
  setCells: (cells) => set({ cells, dirty: false }),
  addCell: (index, type) =>
    set((s) => {
      const cell: Cell = { id: uuidv4(), cell_type: type, source: "", outputs: [], execution_count: null };
      const cells = [...s.cells];
      cells.splice(index, 0, cell);
      return { cells, dirty: true };
    }),
  appendCell: (cell) =>
    set((s) => {
      if (s.cells.some((c) => c.id === cell.id)) return s;
      return { cells: [...s.cells, cell] };
    }),
  updateCellSource: (id, source) =>
    set((s) => ({
      cells: s.cells.map((c) => (c.id === id ? { ...c, source } : c)),
      dirty: true,
    })),
  updateCellOutputs: (id, outputs) =>
    set((s) => {
      const newCounter = s.executionCounter + 1;
      return {
        executionCounter: newCounter,
        cells: s.cells.map((c) =>
          c.id === id ? { ...c, outputs, execution_count: newCounter } : c
        ),
      };
    }),
  deleteCell: (id) =>
    set((s) => ({ cells: s.cells.filter((c) => c.id !== id), dirty: true })),
  moveCell: (id, direction) =>
    set((s) => {
      const idx = s.cells.findIndex((c) => c.id === id);
      if (idx < 0) return s;
      const newIdx = direction === "up" ? idx - 1 : idx + 1;
      if (newIdx < 0 || newIdx >= s.cells.length) return s;
      const cells = [...s.cells];
      [cells[idx], cells[newIdx]] = [cells[newIdx], cells[idx]];
      return { cells, dirty: true };
    }),
  setDirty: (dirty) => set({ dirty }),
  setPipelineRunning: (pipelineRunning) => set({ pipelineRunning }),
  setCurrentPhase: (currentPhase) => set({ currentPhase }),
  setCellExecuting: (id, executing) =>
    set((s) => ({
      cells: s.cells.map((c) => (c.id === id ? { ...c, executing } : c)),
    })),
  setCellError: (id, error) =>
    set((s) => ({
      cells: s.cells.map((c) => (c.id === id ? { ...c, error } : c)),
    })),
  setCellThinking: (id, thinking) =>
    set((s) => ({
      cells: s.cells.map((c) => (c.id === id ? { ...c, thinking } : c)),
    })),
  setLatestThinking: (latestThinking) => set({ latestThinking }),
  hypothesisGroups: [],
  addHypothesisGroup: (id, title) =>
    set((s) => ({
      hypothesisGroups: s.hypothesisGroups.some((g) => g.id === id)
        ? s.hypothesisGroups
        : [...s.hypothesisGroups, { id, title, cellIds: [] }],
    })),
  setAgentActivity: (activity, detail, extra) =>
    set((s) => {
      const entry: ActivityLogEntry = {
        id: s.activityLog.length + 1,
        activity,
        detail,
        phase: s.currentPhase,
        ts: Date.now(),
        ...extra,
      };
      return {
        agentActivity: activity,
        agentActivityDetail: detail,
        activityLog: [...s.activityLog, entry],
      };
    }),
  addChatAction: (detail, actionType) =>
    set((s) => {
      const entry: ActivityLogEntry = {
        id: s.activityLog.length + 1,
        activity: "generating",
        detail,
        phase: "Chat",
        ts: Date.now(),
        chatAction: actionType,
      };
      return { activityLog: [...s.activityLog, entry] };
    }),
  clearActivityLog: () =>
    set({ activityLog: [], agentActivity: "idle" as AgentActivity, agentActivityDetail: "" }),
  resetForNewSession: () =>
    set({
      cells: [],
      dirty: false,
      pipelineRunning: false,
      currentPhase: "",
      executionCounter: 0,
      latestThinking: "",
      agentActivity: "idle" as AgentActivity,
      agentActivityDetail: "",
      activityLog: [],
      hypothesisGroups: [],
      activeTab: "notebook" as "notebook" | "story",
    }),
  activeTab: "notebook" as "notebook" | "story",
  setActiveTab: (activeTab) => set({ activeTab }),
}));
