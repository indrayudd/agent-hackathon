function inferApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  if (typeof window !== "undefined") {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    return `${protocol}//${hostname}:8000/api`;
  }

  return "http://localhost:8000/api";
}

export const API_BASE = inferApiBase();
export const WS_BASE = API_BASE.replace(/^http/, "ws");
