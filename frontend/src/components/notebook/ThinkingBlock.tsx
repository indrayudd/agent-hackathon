"use client";

import { useState } from "react";

interface ThinkingBlockProps {
  content: string;
}

export default function ThinkingBlock({ content }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(true);

  if (!content) return null;

  return (
    <div
      className="mx-4 my-1 px-3 py-2 bg-purple-50 border border-purple-100 rounded-lg cursor-pointer transition-all"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center gap-2">
        <span className="text-purple-400 text-sm">💭</span>
        <span className="text-xs text-purple-600 font-medium">Agent thinking</span>
        <span className="text-purple-300 text-xs ml-auto">{expanded ? "▼" : "▶"}</span>
      </div>
      {expanded && (
        <p className="text-sm text-purple-700 mt-1 italic leading-relaxed">
          {content}
        </p>
      )}
    </div>
  );
}
