"use client";

import { useCallback } from "react";
import { useNotebookStore } from "@/stores/notebookStore";
import type { CellOutput } from "@/lib/types";

type KernelStatus = "disconnected" | "connected" | "busy";

export function useKernel(_sessionId: string) {
  // Derive kernel status from pipeline state instead of hardcoding
  const pipelineRunning = useNotebookStore((s) => s.pipelineRunning);
  const agentActivity = useNotebookStore((s) => s.agentActivity);

  let status: KernelStatus = "disconnected";
  if (pipelineRunning) {
    status = agentActivity === "executing" ? "busy" : "connected";
  } else if (agentActivity === "complete" || agentActivity === "idle") {
    // Pipeline finished — kernel is alive but idle
    status = "connected";
  }

  const executeCell = useCallback(
    async (_cellId: string, _source: string): Promise<CellOutput[]> => {
      return [
        {
          output_type: "stream",
          text: "Cell execution via kernel gateway not yet configured.",
        },
      ];
    },
    []
  );

  return { status, executeCell };
}
