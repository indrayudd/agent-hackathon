"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStoryStore } from "@/stores/storyStore";
import { useNotebookStore } from "@/stores/notebookStore";
import { getStory } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface StoryPaneProps {
  sessionId: string;
}

export default function StoryPane({ sessionId }: StoryPaneProps) {
  const { title, executiveSummary, sections, generatedAt, loading, error } = useStoryStore();
  const pipelineRunning = useNotebookStore((s) => s.pipelineRunning);
  const cells = useNotebookStore((s) => s.cells);
  const setStory = useStoryStore((s) => s.setStory);
  const setLoading = useStoryStore((s) => s.setLoading);
  const setError = useStoryStore((s) => s.setError);
  const [regenerating, setRegenerating] = useState(false);

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const res = await fetch(`${API_BASE}/story/${sessionId}/regenerate`, {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        setStory(data);
      }
    } catch {
      // ignore
    } finally {
      setRegenerating(false);
    }
  };

  useEffect(() => {
    if (!title && !loading && !pipelineRunning) {
      setLoading(true);
      getStory(sessionId, "json")
        .then((data) => {
          if (data) setStory(data);
          else setError("not_found");
        })
        .catch(() => setError("not_found"));
    }
  }, [sessionId, title, loading, pipelineRunning, setStory, setLoading, setError]);

  // Collect ALL plot images (used as fallback if no section has plots)
  const allPlotImages: string[] = [];
  cells.forEach((cell) => {
    cell.outputs?.forEach((o) => {
      const imgData = o.data?.["image/png"];
      if (imgData) allPlotImages.push(imgData);
    });
  });

  if (pipelineRunning) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
        <div className="w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm">Agent is analyzing your data...</p>
        <p className="text-xs text-gray-300">Story will be generated when analysis completes</p>
      </div>
    );
  }

  if (error === "not_found" && !title) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
        <p className="text-sm">No story available yet</p>
        <button
          onClick={() => { setError(null); setLoading(true); getStory(sessionId, "json").then(d => { if (d) setStory(d); else setError("not_found"); }).catch(() => setError("not_found")); }}
          className="text-xs text-blue-500 hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="w-5 h-5 border-2 border-gray-300 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const handleExport = async (format: "pdf" | "md") => {
    try {
      const data = await getStory(sessionId, format);
      if (!data) return;
      const blob = data instanceof Blob ? data : new Blob([typeof data === "string" ? data : JSON.stringify(data)], { type: format === "pdf" ? "application/pdf" : "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `eda-report.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore export errors */ }
  };

  return (
    <div className="h-full overflow-y-auto">
      <article className="max-w-3xl mx-auto px-8 py-10">
        {/* Title + Refresh */}
        <div className="flex items-start justify-between mb-2">
          <h1 className="text-3xl font-bold text-gray-900">{title || "EDA Report"}</h1>
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 hover:border-gray-400 transition-colors disabled:opacity-50 flex-shrink-0 mt-1"
            title="Regenerate story from current notebook"
          >
            {regenerating ? (
              <div className="w-3.5 h-3.5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
            ) : (
              <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2.5 8a5.5 5.5 0 0 1 9.5-3.7" />
                <polyline points="12,1 12,5 8,5" />
                <path d="M13.5 8a5.5 5.5 0 0 1-9.5 3.7" />
                <polyline points="4,15 4,11 8,11" />
              </svg>
            )}
            {regenerating ? "Regenerating..." : "Refresh"}
          </button>
        </div>
        {generatedAt && (
          <p className="text-sm text-gray-400 mb-8">
            Generated {new Date(generatedAt).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })}
          </p>
        )}

        {/* Executive Summary */}
        {executiveSummary && (
          <div className="mb-10 p-5 bg-blue-50 border-l-4 border-blue-400 rounded-r-lg">
            <h2 className="text-sm font-semibold text-blue-700 uppercase tracking-wide mb-2">Key Takeaways</h2>
            <div className="text-gray-700 leading-relaxed text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {executiveSummary.replace(/\\n/g, "\n")}
              </ReactMarkdown>
            </div>
          </div>
        )}

        {/* Narrative Sections with contextual plots */}
        {(() => {
          let anySectionHasPlots = false;
          const rendered = sections.map((section, i) => {
            const sectionCellIds = section.cell_ids || [];
            const sectionPlots: string[] = [];
            cells.forEach((cell) => {
              if (sectionCellIds.includes(cell.id)) {
                cell.outputs?.forEach((o) => {
                  const img = o.data?.["image/png"];
                  if (img) sectionPlots.push(img);
                });
              }
            });
            if (sectionPlots.length > 0) anySectionHasPlots = true;

            return (
              <section key={i} className="mb-10">
                <h2 className="text-xl font-semibold text-gray-800 mb-3 pb-2 border-b border-gray-100">
                  {section.title}
                </h2>
                <div className="text-gray-600 leading-relaxed prose prose-sm max-w-none mb-4">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {(section.content || "").replace(/\\n/g, "\n")}
                  </ReactMarkdown>
                </div>
                {sectionPlots.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                    {sectionPlots.map((img, j) => (
                      <div key={j} className="border border-gray-100 rounded-lg overflow-hidden shadow-sm">
                        <img src={`data:image/png;base64,${img}`} alt={`${section.title} plot ${j + 1}`} className="w-full" />
                      </div>
                    ))}
                  </div>
                )}
              </section>
            );
          });

          return (
            <>
              {rendered}
              {!anySectionHasPlots && allPlotImages.length > 0 && (
                <div className="mb-10">
                  <h2 className="text-lg font-semibold text-gray-800 mb-4">Visualizations</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {allPlotImages.slice(0, 8).map((img, i) => (
                      <div key={i} className="border border-gray-100 rounded-lg overflow-hidden shadow-sm">
                        <img src={`data:image/png;base64,${img}`} alt={`Plot ${i + 1}`} className="w-full" />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          );
        })()}

        {/* Export */}
        <div className="mt-12 pt-6 border-t border-gray-100 flex gap-3">
          <button
            onClick={() => handleExport("pdf")}
            className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800 transition-colors"
          >
            Export PDF
          </button>
          <button
            onClick={() => handleExport("md")}
            className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Export Markdown
          </button>
        </div>
      </article>
    </div>
  );
}
