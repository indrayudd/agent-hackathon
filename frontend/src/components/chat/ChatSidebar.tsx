"use client";

import { useRef, useEffect, useCallback } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useNotebookStore } from "@/stores/notebookStore";
import { useChat } from "@/hooks/useChat";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";

interface ChatSidebarProps {
  sessionId: string;
}

export default function ChatSidebar({ sessionId }: ChatSidebarProps) {
  const messages = useChatStore((s) => s.messages);
  const pipelineRunning = useNotebookStore((s) => s.pipelineRunning);
  const currentPhase = useNotebookStore((s) => s.currentPhase);
  const { sendMessage } = useChat(sessionId);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const handleViewCell = useCallback((cellId: string) => {
    // Find the cell element in the DOM and scroll to it
    const el = document.getElementById(`cell-${cellId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("ring-2", "ring-blue-400");
      setTimeout(() => el.classList.remove("ring-2", "ring-blue-400"), 2000);
    }
  }, []);

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-800">Chat</h2>
        {pipelineRunning && (
          <span className="flex items-center gap-1.5 text-xs text-blue-600">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
            {currentPhase || "Analyzing..."}
          </span>
        )}
      </div>

      <div className="flex-grow overflow-y-auto px-3 py-4">
        {messages.length === 0 && !pipelineRunning && (
          <div className="text-center text-gray-400 text-sm mt-8">
            <p>Ask questions about your data</p>
            <p className="text-xs mt-1">or request additional analysis</p>
          </div>
        )}
        {messages.length === 0 && pipelineRunning && (
          <div className="text-center text-gray-400 text-sm mt-8 px-4">
            <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="font-medium text-gray-600">Agent is analyzing your data</p>
            <p className="text-xs mt-1">Activity will appear here as the analysis progresses</p>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} onViewCell={handleViewCell} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-gray-200">
        <ChatInput onSend={sendMessage} />
      </div>
    </div>
  );
}
