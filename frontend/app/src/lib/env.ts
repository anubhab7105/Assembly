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
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
  NEXT_PUBLIC_APP_MODE: process.env.NEXT_PUBLIC_APP_MODE ?? "dev",
} as const
