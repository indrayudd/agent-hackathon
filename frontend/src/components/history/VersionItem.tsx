"use client";

interface Props {
  versionId: number;
  trigger: string;
  timestamp: string;
  isCurrent: boolean;
  onRestore: () => void;
  restoring: boolean;
}

export default function VersionItem({
  versionId,
  trigger,
  timestamp,
  isCurrent,
  onRestore,
  restoring,
}: Props) {
  return (
    <div className="flex items-start gap-3 py-3">
      {/* Timeline indicator */}
      <div className="flex flex-col items-center pt-1">
        <span
          className={`inline-block w-3 h-3 rounded-full border-2 ${
            isCurrent
              ? "bg-blue-600 border-blue-600"
              : "bg-white border-gray-400"
          }`}
        />
        <div className="w-px flex-grow bg-gray-200 mt-1" />
      </div>

      {/* Content */}
      <div className="flex-grow min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-800">
            v{versionId}
          </span>
          {isCurrent && (
            <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
              Current
            </span>
          )}
        </div>
        <p className="text-sm text-gray-600 truncate">{trigger}</p>
        <p className="text-xs text-gray-400">
          {new Date(timestamp).toLocaleString()}
        </p>
        {!isCurrent && (
          <button
            onClick={onRestore}
            disabled={restoring}
            className="mt-1 text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400 transition-colors"
          >
            {restoring ? "Restoring..." : "Restore"}
          </button>
        )}
      </div>
    </div>
  );
}
