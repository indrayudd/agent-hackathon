"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Props {
  sessionId: string;
}

export default function ExportDialog({ sessionId }: Props) {
  const [open, setOpen] = useState(false);

  const downloadPdf = async () => {
    const res = await fetch(
      `${API_BASE}/story/${sessionId}?format=pdf`
    );
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `story_${sessionId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
    setOpen(false);
  };

  const downloadMarkdown = async () => {
    const res = await fetch(
      `${API_BASE}/story/${sessionId}?format=md`
    );
    if (!res.ok) return;
    const data = await res.json();
    const text = data.markdown || data.content || "";
    const blob = new Blob([text], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `story_${sessionId}.md`;
    a.click();
    URL.revokeObjectURL(url);
    setOpen(false);
  };

  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen(!open)}
        className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors"
      >
        Export
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 bottom-full mb-2 z-50 bg-white border border-gray-200 rounded-lg shadow-lg p-2 min-w-[180px]">
            <button
              onClick={downloadPdf}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded transition-colors"
            >
              Download PDF
            </button>
            <button
              onClick={downloadMarkdown}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded transition-colors"
            >
              Download Markdown
            </button>
          </div>
        </>
      )}
    </div>
  );
}
