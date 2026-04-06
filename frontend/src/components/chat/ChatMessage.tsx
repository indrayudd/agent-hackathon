"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage as ChatMessageType } from "@/lib/types";

interface ChatMessageProps {
  message: ChatMessageType;
  onViewCell?: (cellId: string) => void;
}

export default function ChatMessage({ message, onViewCell }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isAction = message.type === "action";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 ${
          isUser
            ? "bg-blue-600 text-white"
            : isAction
            ? "bg-amber-50 border border-amber-200 text-gray-800"
            : "bg-gray-100 text-gray-800"
        }`}
      >
        {isUser ? (
          <p className="text-sm">{message.content}</p>
        ) : (
          <div className="text-sm prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0.5">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* View Cell button */}
        {message.cell_id && onViewCell && (
          <button
            onClick={() => onViewCell(message.cell_id!)}
            className="mt-1.5 text-xs text-blue-500 hover:text-blue-700 hover:underline flex items-center gap-1"
          >
            <span>📓</span> View in notebook
          </button>
        )}

        <p className={`text-[10px] mt-1 ${isUser ? "text-blue-200" : "text-gray-400"}`}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </p>
      </div>
    </div>
  );
}
