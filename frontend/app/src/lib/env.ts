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
} as const
