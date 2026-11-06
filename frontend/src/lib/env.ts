/**
 * Typed environment configuration (no accounts, no Supabase).
 */

declare global {
  interface Window {
    ASSEMBLY_API_URL?: string
    ASSEMBLY_TOKEN?: string
    ASSEMBLY_APP_MODE?: string
    __TAURI__?: unknown
  }
}

/** True when running inside the Tauri desktop webview. */
export function isDesktop(): boolean {
  return typeof window !== "undefined" && !!window.__TAURI__;
}

/** In desktop mode, the Tauri splash starts the backend and navigates here
 * with `?port=...&token=...` in the URL. Read those into the window globals
 * so the API client points at the dynamic backend endpoint + per-launch
 * token. Secrets live only in the URL (transient), never in
 * localStorage/IndexedDB/sessionStorage. */
function initDesktopFromUrl(): void {
  if (!isDesktop() || typeof window === "undefined") {
    return;
  }
  try {
    const params = new URLSearchParams(window.location.search);
    const port = params.get("port");
    const token = params.get("token");
    if (port && !window.ASSEMBLY_API_URL) {
      window.ASSEMBLY_API_URL = `http://127.0.0.1:${port}`;
    }
    if (token && !window.ASSEMBLY_TOKEN) {
      window.ASSEMBLY_TOKEN = token;
    }
    if (port || token) {
      // App mode is desktop when launched from the Tauri shell.
      window.ASSEMBLY_APP_MODE = "desktop";
    }
  } catch {
    // URL parsing must never break the app.
  }
}

initDesktopFromUrl();

export const env = {
  /** Base URL for the Assembly FastAPI backend. No trailing slash. */
  get apiUrl() {
    if (typeof window !== "undefined" && window.ASSEMBLY_API_URL) {
      return window.ASSEMBLY_API_URL;
    }
    return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  },
  get desktopToken() {
    if (typeof window !== "undefined" && window.ASSEMBLY_TOKEN) {
      return window.ASSEMBLY_TOKEN;
    }
    return "";
  },
  get NEXT_PUBLIC_APP_MODE() {
    if (typeof window !== "undefined" && window.ASSEMBLY_APP_MODE) {
      return window.ASSEMBLY_APP_MODE;
    }
    return process.env.NEXT_PUBLIC_APP_MODE || "dev";
  },
}
