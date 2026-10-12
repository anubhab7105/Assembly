/**
 * Typed environment configuration (no accounts, no Supabase).
 */

declare global {
  interface Window {
    ASSEMBLY_API_URL?: string
    ASSEMBLY_TOKEN?: string
    ASSEMBLY_APP_MODE?: string
  }
}

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
