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
    <div className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      {isUser ? (
        <div className="w-6 h-6 rounded bg-secondary-container flex items-center justify-center shrink-0">
          <span className="material-symbols-outlined text-on-secondary-container text-sm">person</span>
        </div>
      ) : (
        <div className="w-6 h-6 rounded bg-primary/10 flex items-center justify-center shrink-0">
          <span className="material-symbols-outlined text-primary text-sm">smart_toy</span>
        </div>
      )}

      {/* Bubble */}
      <div
        className={`max-w-[85%] p-3 ${
          isUser
            ? "bg-primary text-white rounded-2xl rounded-tr-none chat-shadow"
            : isAction
            ? "bg-surface-container-lowest rounded-2xl rounded-tl-none chat-shadow border border-outline-variant/5"
            : "bg-surface-container-lowest rounded-2xl rounded-tl-none chat-shadow border border-outline-variant/5"
        }`}
      >
        {isUser ? (
          <p className="text-sm font-body leading-6 whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="space-y-2">
            {isAction && (
              <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-primary">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                Agent update
              </div>
            )}
            <div className="text-sm font-body text-on-surface prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0.5 prose-pre:my-2 prose-code:rounded prose-code:bg-surface-container prose-code:px-1.5 prose-code:py-0.5 prose-code:before:content-none prose-code:after:content-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          </div>
        )}

        {message.cell_id && onViewCell && (
          <button
            onClick={() => onViewCell(message.cell_id!)}
            className="mt-1.5 inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            <span className="material-symbols-outlined text-xs">description</span>
            View in notebook
          </button>
        )}

        <p className={`text-[10px] mt-1 ${isUser ? "text-white/60" : "text-on-surface-variant"}`}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </p>
      </div>
    </div>
  );
}
