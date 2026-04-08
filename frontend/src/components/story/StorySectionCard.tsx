"use client";

import { useState } from "react";
import type { CSSProperties } from "react";
import type { StorySection } from "@/lib/types";
import type { StoryPlot } from "@/lib/types";
import StoryMarkdown from "./StoryMarkdown";
import PlotCarousel from "./PlotCarousel";

interface Props {
  section: StorySection;
  plots?: Array<StoryPlot | string>;
  plotCellIds?: string[];
  onOpenCell?: (cellId: string) => void;
  index?: number;
}

function phaseIcon(phase: string): string {
  const p = phase.toLowerCase();
  if (p.includes('loading') || p.includes('ingestion')) return 'download';
  if (p.includes('cleaning')) return 'cleaning_services';
  if (p.includes('univariate')) return 'bar_chart';
  if (p.includes('dynamic') || p.includes('time')) return 'timeline';
  if (p.includes('correlation')) return 'hub';
  if (p.includes('outlier')) return 'warning';
  if (p.includes('hypothesis') || p.includes('investigation')) return 'science';
  return 'insights';
}

export default function StorySectionCard({
  section,
  plots,
  plotCellIds = [],
  onOpenCell,
  index = 0,
}: Props) {
  const [expanded, setExpanded] = useState(false);

  const sectionInsights = section.insights ?? [];
  const sectionPlots = plots ?? section.plots ?? [];

  const content = (section.summary || section.content || "")
    .replace(/\\n/g, "\n")
    .trim();
  const paragraphs = content
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
  const intro = section.subtitle || paragraphs[0] || "";
  const bodyParagraphs =
    intro && paragraphs[0] === intro ? paragraphs.slice(1) : paragraphs;

  const visibleParagraphs = expanded ? bodyParagraphs : bodyParagraphs.slice(0, 2);
  const hasMore = bodyParagraphs.length > 2;

  const phaseLower = section.phase?.toLowerCase() || '';
  const isHighlighted =
    phaseLower.includes('hypothesis') ||
    phaseLower.includes('conclusion') ||
    phaseLower.includes('investigation');

  return (
    <section
      className={`report-section animate-rise-in pt-8 ${
        isHighlighted
          ? 'border-l-4 border-primary pl-6'
          : 'border-t border-outline-variant/18 pt-10'
      }`}
      style={{ "--story-delay": `${index * 80}ms` } as CSSProperties}
    >
      <div className="max-w-4xl">
        {/* Phase badge with icon */}
        {section.phase && (
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.24em] text-primary">
            <span className="material-symbols-outlined text-[13px]">
              {phaseIcon(section.phase)}
            </span>
            <span>{section.phase}</span>
          </div>
        )}

        <h3 className="mt-2 text-2xl font-bold tracking-tight text-on-surface sm:text-3xl">
          {section.title}
        </h3>

        {intro && (
          <div className="mt-3 max-w-3xl text-[15px] leading-7">
            <StoryMarkdown content={intro} className="text-on-surface-variant" />
          </div>
        )}

        {visibleParagraphs.length > 0 && (
          <div className="mt-5 space-y-4">
            {visibleParagraphs.map((para, i) => (
              <StoryMarkdown key={i} content={para} className="story-prose text-on-surface-variant" />
            ))}
          </div>
        )}

        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-primary font-medium mt-2 hover:underline"
          >
            {expanded ? "Show less" : `Read more (${bodyParagraphs.length - 2} more paragraphs)`}
          </button>
        )}

        {section.tags && section.tags.length > 0 && (
          <p className="mt-5 text-[10px] uppercase tracking-[0.22em] text-on-surface-variant">
            {section.tags.join(" · ")}
          </p>
        )}
      </div>

      {sectionPlots.length > 0 && (
        <div className="mt-8">
          <PlotCarousel
            plots={sectionPlots}
            section={section}
            plotCellIds={plotCellIds}
            onOpenCell={onOpenCell}
          />
        </div>
      )}

      {sectionInsights.length > 0 && (
        <div className="mt-6 flex flex-wrap gap-2">
          {sectionInsights.map((insight, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1.5 rounded-full border border-outline-variant/20 bg-surface-container-low/60 px-3 py-1.5 text-xs text-on-surface-variant"
            >
              <span className="material-symbols-outlined text-[14px] text-primary">lightbulb</span>
              <span className="font-medium text-on-surface">{insight.type}</span>
              <span className="hidden sm:inline">
                — {insight.description.slice(0, 80)}{insight.description.length > 80 ? '…' : ''}
              </span>
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
