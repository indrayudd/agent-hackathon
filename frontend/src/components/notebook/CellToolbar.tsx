"use client";

interface Props {
  cellType: "code" | "markdown";
  onRun: () => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

export default function CellToolbar({
  cellType,
  onRun,
  onDelete,
  onMoveUp,
  onMoveDown,
}: Props) {
  const btnClass =
    "px-2 py-0.5 text-xs text-gray-500 hover:text-gray-800 hover:bg-gray-100 rounded transition-colors";

  return (
    <div className="flex items-center gap-1 py-1 px-2">
      <button className={btnClass} onClick={onRun} title="Run cell">
        &#9654;
      </button>
      <button className={btnClass} onClick={onMoveUp} title="Move up">
        &uarr;
      </button>
      <button className={btnClass} onClick={onMoveDown} title="Move down">
        &darr;
      </button>
      <button className={btnClass} onClick={onDelete} title="Delete cell">
        &#128465;
      </button>
      <span className="ml-auto text-[10px] text-gray-400 uppercase tracking-wide">
        {cellType}
      </span>
    </div>
  );
}
