const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function uploadFile(file: File): Promise<any> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  return res.json();
}

export async function listSessions(): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions`);
  return res.json();
}

export async function getNotebook(sessionId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/notebook/${sessionId}`);
  if (!res.ok) return null;
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/session/${sessionId}`, { method: "DELETE" });
}

export async function runEda(sessionId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/run/${sessionId}`, { method: "POST" });
  return res.json();
}

export async function getStory(sessionId: string, format: "json" | "md" | "pdf" = "json"): Promise<any> {
  const res = await fetch(`${API_BASE}/story/${sessionId}?format=${format}`);
  if (!res.ok) return null;
  return format === "pdf" ? res.blob() : res.json();
}
