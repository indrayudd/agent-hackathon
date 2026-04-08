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
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-outline-variant hover:border-outline"
        } bg-surface-container-lowest`}
      >
        <input {...getInputProps()} />
        {file ? (
          <div>
            <span className="material-symbols-outlined text-primary text-3xl mb-2">description</span>
            <p className="font-medium text-on-surface font-body">{file.name}</p>
            <p className="text-sm text-on-surface-variant font-body">{formatSize(file.size)}</p>
          </div>
        ) : (
          <div>
            <span className="material-symbols-outlined text-on-surface-variant text-3xl mb-2">upload_file</span>
            <p className="text-on-surface-variant font-body">
              {isDragActive ? "Drop the file here..." : "Drag & drop a dataset, or click to browse"}
            </p>
          </div>
        )}
      </div>

      {error && <p className="text-error text-sm font-body">{error}</p>}

      <button
        onClick={handleRun}
        disabled={!file || uploading}
        className="px-6 py-2.5 rounded-lg bg-primary text-on-primary font-medium hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-body"
      >
        {uploading ? "Uploading..." : "Run EDA"}
      </button>
    </div>
  );
}
