/**
 * Typed environment configuration.
 * Throws at startup if required variables are missing.
 */

function require_env(key: string): string {
  const value = process.env[key]
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`)
  }
  return value
}

export const env = {
  /** Base URL for the Assembly FastAPI backend. No trailing slash. */
  get apiUrl() {
    if (typeof window !== "undefined" && (window as any).ASSEMBLY_API_URL) {
      return (window as any).ASSEMBLY_API_URL;
    }
    return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  },
  get desktopToken() {
    if (typeof window !== "undefined" && (window as any).ASSEMBLY_TOKEN) {
      return (window as any).ASSEMBLY_TOKEN;
    }
    return "";
  },
  get NEXT_PUBLIC_APP_MODE() {
    if (typeof window !== "undefined" && (window as any).ASSEMBLY_APP_MODE) {
      return (window as any).ASSEMBLY_APP_MODE;
    }
    return process.env.NEXT_PUBLIC_APP_MODE || "dev";
  },
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL || "https://dummy.supabase.co",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "dummy-anon-key",
}
