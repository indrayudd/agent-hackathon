"use client";
import { useEffect, useRef } from "react";
import { useNotebookStore } from "@/stores/notebookStore";
import { useStoryStore } from "@/stores/storyStore";
import { useChatStore } from "@/stores/chatStore";
import type { Cell } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export function useAgentStream(sessionId: string) {
  const connected = useRef<string | null>(null);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (connected.current === sessionId) return;
    // Close previous WebSocket if switching sessions
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
    connected.current = sessionId;

    try {
      const socket = new WebSocket(`${WS_BASE}/stream/${sessionId}`);
      ws.current = socket;

      socket.onopen = () => {
        useNotebookStore.getState().setPipelineRunning(true);
        useNotebookStore.getState().clearActivityLog();
        useNotebookStore.getState().setAgentActivity("thinking", "Starting EDA analysis...");
        useChatStore.getState().addAgentMessage("Starting EDA analysis...", "text");
      };

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const store = useNotebookStore.getState();
        const chat = useChatStore.getState();

        switch (data.type) {
          case "thinking":
            store.setLatestThinking(data.content || "");
            store.setAgentActivity("thinking", data.content || "Thinking...");
            break;

          case "cell_write": {
            // Extract hypothesis ID first (needed for activity log)
            const hypMatch = data.cell_id?.match(/^(h\d+)_/);
            const hypId = hypMatch ? hypMatch[1] : undefined;

            const cell: Cell = {
              id: data.cell_id,
              cell_type: data.cell_type || "code",
              source: data.source || "",
              outputs: [],
              execution_count: null,
              executing: false,
              error: null,
            };
            store.appendCell(cell);
            store.setLatestThinking("");  // clear thinking when cell appears
            store.setAgentActivity("generating", data.source || "", {
              cellId: data.cell_id,
              cellType: (data.cell_type as "code" | "markdown") || "code",
              hypothesisId: hypId,
            });

            // Track hypothesis grouping
            if (hypId) {
              const groups = store.hypothesisGroups;
              const group = groups.find((g: { id: string }) => g.id === hypId);
              if (group) {
                group.cellIds.push(data.cell_id);
              }
            }
            break;
          }

          case "cell_executing":
            store.setCellExecuting(data.cell_id, true);
            store.setAgentActivity("executing", "Running cell...", { cellId: data.cell_id });
            break;

          case "cell_output":
            store.setCellExecuting(data.cell_id, false);
            store.updateCellOutputs(data.cell_id, data.outputs || []);
            // Show brief status for significant outputs
            const outputText = (data.outputs || [])
                .map((o: any) => o.text || o.data?.["text/plain"] || "")
                .join("")
                .trim();
            if (outputText && outputText.length > 10) {
                const firstLine = outputText.split("\n")[0].slice(0, 80);
                store.setLatestThinking(firstLine);
            }
            break;

          case "cell_error":
            store.setCellExecuting(data.cell_id, false);
            store.setCellError(data.cell_id, data.error || "Unknown error");
            if (data.traceback) {
              store.updateCellOutputs(data.cell_id, [{
                output_type: "error",
                ename: "Error",
                evalue: data.error,
                traceback: Array.isArray(data.traceback) ? data.traceback.flat() : [],
              }]);
            }
            chat.addAgentMessage("Error: " + (data.error || "Unknown error") + ". Attempting fix...", "text");
            store.setAgentActivity("fixing", data.error || "Unknown error", { cellId: data.cell_id });
            break;

          case "cell_update":
            store.updateCellSource(data.cell_id, data.source || "");
            store.setAgentActivity("generating", `Edited cell`, { cellId: data.cell_id });
            break;

          case "cell_delete":
            store.deleteCell(data.cell_id);
            break;

          case "cell_reorder":
            store.moveCell(data.cell_id, data.direction || "down");
            break;

          case "chat_action":
            store.setAgentActivity("generating", data.detail || "User action", {
              cellId: data.cell_id,
            });
            store.addChatAction(data.detail || "Action", data.action || "unknown");
            break;

          case "phase_transition":
            store.setCurrentPhase(data.phase || "");
            store.setAgentActivity("thinking", data.phase || "", {
              hypothesisId: data.notebook_id || undefined,
            });
            if (data.notebook_id) {
              store.addHypothesisGroup(data.notebook_id, data.phase || "");
            }
            break;

          case "backtrack":
            store.setLatestThinking(`⟲ Backtracking: ${data.reason}`);
            store.setAgentActivity("backtracking", data.reason || "");
            chat.addAgentMessage("Backtracking: " + data.reason, "text");
            break;

          case "complete":
            store.setPipelineRunning(false);
            store.setCurrentPhase("");
            store.setLatestThinking("");
            store.setAgentActivity("complete", "EDA complete");
            chat.addAgentMessage(
              "EDA complete! Switch to the **Story** tab for the full narrative report, or ask me questions about the data.",
              "text",
            );
            // Fetch story after a short delay to give backend time to write it
            setTimeout(() => {
              fetch(`${API_BASE}/story/${sessionId}?format=json`)
                .then((r) => (r.ok ? r.json() : null))
                .then((story) => {
                  if (story) useStoryStore.getState().setStory(story);
                })
                .catch(() => {});
            }, 1000);
            break;
        }
      };

      socket.onclose = () => {
        ws.current = null;
      };

      socket.onerror = () => {
        // WebSocket may fail on first try if agent hasn't started yet — retry once
        setTimeout(() => {
          if (!ws.current || ws.current.readyState === WebSocket.CLOSED) {
            connected.current = null;
            // The useEffect will re-run on next render cycle
          }
        }, 2000);
      };
    } catch {
      console.warn("Stream WebSocket not available");
    }

    return () => {
      // Don't close the socket on cleanup from strict-mode remount
      // Only close if component is truly unmounting
    };
  }, [sessionId]);
}
