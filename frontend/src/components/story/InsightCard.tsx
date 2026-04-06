"use client";

import type { InsightCard as InsightCardType } from "@/lib/types";

const BADGE_COLORS: Record<string, string> = {
  TREND: "bg-blue-100 text-blue-800",
  OUTLIER: "bg-red-100 text-red-800",
  CORRELATION: "bg-purple-100 text-purple-800",
  CAUSAL: "bg-green-100 text-green-800",
  DISTRIBUTION: "bg-yellow-100 text-yellow-800",
  MISSING: "bg-gray-100 text-gray-800",
};

interface Props {
  insight: InsightCardType;
}

export default function InsightCard({ insight }: Props) {
  const badgeClass =
    BADGE_COLORS[insight.type.toUpperCase()] || "bg-gray-100 text-gray-700";

  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-white">
      <div className="flex items-center gap-2 mb-1">
        <span
          className={`text-xs font-semibold px-2 py-0.5 rounded-full ${badgeClass}`}
        >
          {insight.type}
        </span>
        {insight.confidence != null && (
          <span className="text-xs text-gray-400 ml-auto">
            {Math.round(insight.confidence * 100)}% confidence
          </span>
        )}
      </div>
      <p className="text-sm text-gray-700 mb-1">{insight.description}</p>
      <p className="text-xs text-gray-400">
        Phase: {insight.phase} &middot; Rule #{insight.rule}
      </p>
      {insight.confidence != null && (
        <div className="mt-2 h-1 w-full rounded-full bg-gray-100">
          <div
            className="h-1 rounded-full bg-blue-500"
            style={{ width: `${Math.round(insight.confidence * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
