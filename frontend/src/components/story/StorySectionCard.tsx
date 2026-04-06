"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { StorySection } from "@/lib/types";
import InsightCard from "./InsightCard";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Props {
  section: StorySection;
}

export default function StorySectionCard({ section }: Props) {
  const [open, setOpen] = useState(true);

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
      >
        <span
          className={`text-gray-400 transition-transform ${open ? "rotate-90" : ""}`}
        >
          &#9656;
        </span>
        <span className="font-medium text-gray-800 text-sm">
          {section.title}
        </span>
        <span className="ml-auto text-xs text-gray-400">{section.phase}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          <div className="prose prose-sm max-w-none text-gray-700">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {section.content}
            </ReactMarkdown>
          </div>

          {section.plots.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {section.plots.map((plot, i) => (
                <img
                  key={i}
                  src={
                    plot.startsWith("http")
                      ? plot
                      : `${API_BASE}/plots/${plot}`
                  }
                  alt={`Plot ${i + 1}`}
                  className="rounded border border-gray-200 max-h-64 object-contain"
                />
              ))}
            </div>
          )}

          {section.insights.length > 0 && (
            <div className="space-y-2 pt-2">
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Insights
              </h4>
              {section.insights.map((insight, i) => (
                <InsightCard key={i} insight={insight} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
