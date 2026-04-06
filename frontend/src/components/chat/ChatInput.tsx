"use client";

import { useState, useCallback } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useNotebookStore } from "@/stores/notebookStore";

interface ChatInputProps {
  onSend: (content: string) => void;
}

export default function ChatInput({ onSend }: ChatInputProps) {
  const [value, setValue] = useState("");
  const isTyping = useChatStore((s) => s.isTyping);
  const pipelineRunning = useNotebookStore((s) => s.pipelineRunning);
  const addUserMessage = useChatStore((s) => s.addUserMessage);

  const submit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isTyping) return;
    addUserMessage(trimmed);
    onSend(trimmed);
    setValue("");
  }, [value, isTyping, addUserMessage, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-gray-200 p-2">
      <div className="flex gap-2">
        <textarea
          className="flex-1 resize-none rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
          rows={2}
          placeholder={pipelineRunning ? "Agent is running EDA..." : "Ask about your data..."}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isTyping}
        />
        <button
          className="self-end rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          onClick={submit}
          disabled={isTyping || !value.trim()}
        >
          Send
        </button>
      </div>
      {isTyping && (
        <p className="mt-1 text-xs text-gray-400">Agent is typing...</p>
      )}
    </div>
  );
}
