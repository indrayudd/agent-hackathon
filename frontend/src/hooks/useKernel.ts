"use client";

import { useState, useCallback } from "react";
import type { CellOutput } from "@/lib/types";

type KernelStatus = "disconnected" | "connected" | "busy";

export function useKernel(_sessionId: string) {
  const [status] = useState<KernelStatus>("disconnected");

  const executeCell = useCallback(
    async (_cellId: string, _source: string): Promise<CellOutput[]> => {
      // Real implementation will connect to ws://localhost:8000/api/kernel/{sessionId}/channels
      return [
        {
          output_type: "stream",
          text: "Kernel not connected. Cell execution will be available when the kernel gateway is configured.",
        },
      ];
    },
    []
  );

  return { status, executeCell };
}
