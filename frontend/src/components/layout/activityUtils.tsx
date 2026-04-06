import type { ComponentType } from "react";
import type { AgentActivity } from "@/stores/notebookStore";

/* ── Cell source summarizer ─────────────────────────────── */

export function summarizeCellSource(source: string, cellType?: "code" | "markdown"): string {
  if (!source) return "Empty cell";

  if (cellType === "markdown") {
    const heading = source.match(/^#+\s+(.+)/m);
    if (heading) return heading[1].slice(0, 40);
    return source.slice(0, 40).replace(/\n/g, " ");
  }

  // Code patterns — priority order
  const patterns: [RegExp, string | ((m: RegExpMatchArray) => string)][] = [
    [/pd\.read_csv\(["'](.+?)["']\)/, (m) => `Load ${m[1]}`],
    [/pd\.read_excel\(["'](.+?)["']\)/, (m) => `Load ${m[1]}`],
    [/\.hist\(/, "Plot distributions"],
    [/\.imshow\(|sns\.heatmap/, "Correlation heatmap"],
    [/\.corr\(\)/, "Compute correlations"],
    [/rolling.*mean|rolling.*std/, "Rolling statistics"],
    [/axes.*\.plot\(|\.plot\(/, "Time series plot"],
    [/day_name|\.dt\.hour|\.dt\.dayofweek/, "Seasonality analysis"],
    [/\.dtypes/, "Inspect column types"],
    [/\.describe\(/, "Statistical summary"],
    [/\.isnull\(\)\.sum\(\)|\.isna\(\)\.sum\(\)/, "Check missing values"],
    [/pd\.to_datetime\(df\[["'](.+?)["']\]/, (m) => `Parse '${m[1]}' as datetime`],
    [/pd\.to_datetime/, "Parse datetime"],
    [/\.interpolate\(/, "Interpolate missing values"],
    [/\.ffill\(/, "Forward-fill missing values"],
    [/\.dropna\(/, "Drop missing rows"],
    [/IQR|quantile.*0\.25/, "Outlier detection (IQR)"],
    [/split_idx|train_test_split/, "Train/test split"],
    [/list\(df\.columns\)/, "List columns"],
    [/df\.head\(/, "Preview data"],
    [/df\.info\(/, "Dataset info"],
    [/df\.shape/, "Check shape"],
    [/plt\.figure|plt\.subplots|fig,/, "Create plot"],
    [/scatter\(/, "Scatter plot"],
    [/boxplot\(|\.box\(/, "Box plot"],
    [/groupby\(/, "Group-by aggregation"],
    [/value_counts/, "Count values"],
    [/scipy\.stats|ttest|mannwhitneyu|pearsonr/, "Statistical test"],
  ];

  for (const [regex, label] of patterns) {
    const match = source.match(regex);
    if (match) {
      return typeof label === "function" ? label(match) : label;
    }
  }

  // Fallback: first non-import, non-comment line
  const lines = source.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith("import ") && !trimmed.startsWith("from ") && !trimmed.startsWith("#")) {
      return trimmed.slice(0, 40);
    }
  }
  return lines[0]?.startsWith("import") ? "Import libraries" : source.slice(0, 40);
}

/* ── SVG Icons (16x16, currentColor) ────────────────────── */

export function ThinkingIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" />
      <circle cx="5.5" cy="8" r="0.75" fill="currentColor" stroke="none" />
      <circle cx="8" cy="8" r="0.75" fill="currentColor" stroke="none" />
      <circle cx="10.5" cy="8" r="0.75" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function CodeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="5,4 2,8 5,12" />
      <polyline points="11,4 14,8 11,12" />
      <line x1="9" y1="3" x2="7" y2="13" />
    </svg>
  );
}

export function PlayIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="currentColor" stroke="none">
      <polygon points="4,2 14,8 4,14" />
    </svg>
  );
}

export function WrenchIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.5 2.5a3.5 3.5 0 0 0-3.2 4.8L3 11.6V14h2.4l4.3-4.3a3.5 3.5 0 0 0 4.8-3.2l-2 2-1.5-1.5 2-2z" />
    </svg>
  );
}

export function RetryIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 8a5.5 5.5 0 0 1 9.5-3.7" />
      <polyline points="12,1 12,5 8,5" />
      <path d="M13.5 8a5.5 5.5 0 0 1-9.5 3.7" />
      <polyline points="4,15 4,11 8,11" />
    </svg>
  );
}

export function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" />
      <polyline points="5.5,8 7.5,10 10.5,6" />
    </svg>
  );
}

export function MarkdownIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="3" width="14" height="10" rx="1" />
      <polyline points="4,10 4,6 6.5,8.5 9,6 9,10" />
      <polyline points="11,8.5 12.5,10 14,8.5" />
    </svg>
  );
}

export function HypothesisIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 2v5.5L4 12a1.5 1.5 0 0 0 1.3 2h5.4a1.5 1.5 0 0 0 1.3-2L10 7.5V2" />
      <line x1="5" y1="2" x2="11" y2="2" />
      <line x1="4.5" y1="10" x2="11.5" y2="10" />
    </svg>
  );
}

/* ── Activity config ────────────────────────────────────── */

interface ActivityConfig {
  Icon: ComponentType<{ className?: string }>;
  color: string;
  dotColor: string;
  ringColor: string;
}

export const ACTIVITY_CONFIG: Record<AgentActivity, ActivityConfig> = {
  idle:         { Icon: ThinkingIcon, color: "text-gray-400",    dotColor: "bg-gray-300",    ringColor: "ring-gray-200" },
  thinking:     { Icon: ThinkingIcon, color: "text-purple-600",  dotColor: "bg-purple-400",  ringColor: "ring-purple-300" },
  generating:   { Icon: CodeIcon,     color: "text-blue-600",    dotColor: "bg-blue-500",    ringColor: "ring-blue-300" },
  executing:    { Icon: PlayIcon,     color: "text-amber-600",   dotColor: "bg-amber-400",   ringColor: "ring-amber-300" },
  fixing:       { Icon: WrenchIcon,   color: "text-red-600",     dotColor: "bg-red-400",     ringColor: "ring-red-300" },
  backtracking: { Icon: RetryIcon,    color: "text-orange-600",  dotColor: "bg-orange-400",  ringColor: "ring-orange-300" },
  complete:     { Icon: CheckIcon,    color: "text-green-600",   dotColor: "bg-green-500",   ringColor: "ring-green-300" },
};
