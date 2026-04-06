"use client";

import { useState, useCallback, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import ThreeColumnLayout from "@/components/layout/ThreeColumnLayout";
import TabBar from "@/components/layout/TabBar";
import NotebookPane from "@/components/notebook/NotebookPane";
import StoryPane from "@/components/story/StoryPane";
import HistoryPanel from "@/components/history/HistoryPanel";
import ChatSidebar from "@/components/chat/ChatSidebar";
import AgentActivityBadge from "@/components/layout/AgentActivityBadge";
import { useNotebookStore } from "@/stores/notebookStore";
import { useAgentStream } from "@/hooks/useAgentStream";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export default function SessionPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const activeTab = useNotebookStore((s) => s.activeTab);
  const setActiveTab = useNotebookStore((s) => s.setActiveTab);
  const [showHistory, setShowHistory] = useState(false);
  const [sessionMeta, setSessionMeta] = useState<any>(null);
  const dirty = useNotebookStore((s) => s.dirty);
  const cellCount = useNotebookStore((s) => s.cells.length);
  const hypothesisGroups = useNotebookStore((s) => s.hypothesisGroups);

  // Reset store when entering a new session (new CSV upload)
  useEffect(() => {
    useNotebookStore.getState().resetForNewSession();
  }, [params.id]);

  // Connect to the agent stream for real-time cell updates
  useAgentStream(params.id);

  // Fetch session metadata for files sidebar
  useEffect(() => {
    fetch(`${API_BASE}/sessions`)
      .then((r) => r.json())
      .then((data) => {
        const session = (data.sessions || []).find(
          (s: any) => s.session_id === params.id
        );
        if (session) setSessionMeta(session);
      })
      .catch(() => {});
  }, [params.id]);

  const handleConfirm = useCallback(() => {
    fetch(`${API_BASE}/notebook/${params.id}/confirm`, { method: "POST" })
      .then(() => useNotebookStore.getState().setDirty(false))
      .catch(() => {});
  }, [params.id]);

  const left = (
    <div className="p-3">
      <button
        onClick={() => router.push("/")}
        className="text-sm text-blue-500 hover:underline mb-4 block"
      >
        &larr; Back
      </button>
      <h2 className="text-sm font-semibold text-gray-800 mb-3">Files</h2>
      {sessionMeta ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 p-2 rounded bg-blue-50 border border-blue-100">
            <span className="text-lg">📄</span>
            <div className="min-w-0">
              <p className="text-xs font-medium text-gray-800 truncate">
                {sessionMeta.original_filename}
              </p>
              <p className="text-[10px] text-gray-500">
                {sessionMeta.row_count} rows · {sessionMeta.col_count} cols · {sessionMeta.source_format}
              </p>
            </div>
          </div>
          {cellCount > 0 && (
            <div className="flex items-center gap-2 p-2 rounded bg-green-50 border border-green-100">
              <span className="text-lg">📓</span>
              <div>
                <p className="text-xs font-medium text-gray-800">notebook.ipynb</p>
                <p className="text-[10px] text-gray-500">{cellCount} cells</p>
              </div>
            </div>
          )}
          {hypothesisGroups.map((g) => (
            <div key={g.id} className="flex items-center gap-2 p-2 rounded bg-purple-50 border border-purple-100 mt-1">
              <span className="text-lg">🔬</span>
              <div className="min-w-0">
                <p className="text-xs font-medium text-gray-800 truncate">{g.title}</p>
                <p className="text-[10px] text-gray-500">{g.cellIds.length} cells</p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-400">Session: {params.id.slice(0, 8)}...</p>
      )}
      <AgentActivityBadge />
    </div>
  );

  const center = (
    <div className="relative flex flex-col h-full">
      <TabBar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        dirty={dirty}
        onConfirm={handleConfirm}
        onHistory={() => setShowHistory((v) => !v)}
      />

      <div className="flex-grow overflow-hidden">
        {activeTab === "notebook" ? (
          <NotebookPane />
        ) : (
          <StoryPane sessionId={params.id} />
        )}
      </div>
      {showHistory && (
        <HistoryPanel
          sessionId={params.id}
          onClose={() => setShowHistory(false)}
        />
      )}
    </div>
  );

  const right = <ChatSidebar sessionId={params.id} />;

  return <ThreeColumnLayout left={left} center={center} right={right} />;
}
