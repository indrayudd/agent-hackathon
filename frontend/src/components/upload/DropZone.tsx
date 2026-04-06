"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useRouter } from "next/navigation";
import { uploadFile, runEda } from "@/lib/api";

const ACCEPTED: Record<string, string[]> = {
  "text/csv": [".csv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.ms-excel": [".xls"],
  "application/json": [".json"],
  "application/x-ndjson": [".jsonl", ".ndjson"],
  "application/octet-stream": [".parquet"],
  "text/plain": [".log", ".txt", ".tsv"],
};

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DropZone() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback((accepted: File[]) => {
    setError(null);
    if (accepted.length > 0) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    multiple: false,
  });

  const handleRun = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const data = await uploadFile(file);
      // Navigate first so the stream WebSocket connects before events flow
      // runEda is fire-and-forget (202 Accepted), so no need to await the result
      runEda(data.session_id).catch(() => {});
      router.push(`/session/${data.session_id}`);
    } catch (err: any) {
      setError(err.message ?? "Upload failed");
      setUploading(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-4 w-full max-w-lg">
      <div
        {...getRootProps()}
        className={`w-full border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
          isDragActive ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400"
        }`}
      >
        <input {...getInputProps()} />
        {file ? (
          <div>
            <p className="font-medium text-gray-800">{file.name}</p>
            <p className="text-sm text-gray-500">{formatSize(file.size)}</p>
          </div>
        ) : (
          <p className="text-gray-500">
            {isDragActive ? "Drop the file here..." : "Drag & drop a dataset, or click to browse"}
          </p>
        )}
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      <button
        onClick={handleRun}
        disabled={!file || uploading}
        className="px-6 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {uploading ? "Uploading..." : "Run EDA"}
      </button>
    </div>
  );
}
