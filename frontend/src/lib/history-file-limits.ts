/** Maximum allowed size for external/untrusted history import files (5 MiB). */
export const MAX_HISTORY_FILE_SIZE = 5 * 1024 * 1024

/** Maximum number of history entries retained and accepted in Assembly v1 backups. */
export const MAX_HISTORY = 200

/** Maximum number of usage entries retained and accepted in Assembly v1 backups. */
export const MAX_USAGE = 200

/** Maximum allowed character count for a question in a history record. */
export const MAX_QUESTION_CHARS = 4_000

/** Maximum allowed character count for an answer in a history record (~50,000 words). */
export const MAX_ANSWER_CHARS = 250_000

/**
 * Hard bound for Assembly version-1 history exports and backup restoration (50 MiB).
 * Enforces a consistent contract across saveHistory, exportJSON, and importJSON:
 * saveHistory and importJSON enforce that the total serialized backup size
 * (accounting for the version-and-usage envelope and 2-space indentation)
 * never exceeds MAX_BACKUP_EXPORT_BYTES, guaranteeing that all saved history
 * is always exportable and restorable.
 */
export const MAX_BACKUP_IMPORT_BYTES = 50 * 1024 * 1024
export const MAX_BACKUP_EXPORT_BYTES = MAX_BACKUP_IMPORT_BYTES

/** Human-readable MiB value for backup limit error messages. */
export const MAX_BACKUP_IMPORT_MIB = Math.round(MAX_BACKUP_IMPORT_BYTES / (1024 * 1024))

/**
 * Serializes history and usage records into the canonical Assembly version-1 backup JSON string.
 * Uses 2-space indentation matching exportJSON.
 */
export function serializeAssemblyBackup(history: unknown[], usage: unknown[]): string {
  return JSON.stringify({ version: 1, history, usage }, null, 2)
}

/**
 * Calculates the UTF-8 byte length of a version-1 backup payload.
 */
export function calculateBackupSerializedBytes(history: unknown[], usage: unknown[]): number {
  const payload = serializeAssemblyBackup(history, usage)
  return new TextEncoder().encode(payload).byteLength
}

/** Validates the strict top-level shape of an Assembly version-1 backup envelope. */
export function isAssemblyBackupEnvelope(raw: unknown): raw is {
  version: 1
  history: unknown[]
  usage: unknown[]
} {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return false
  const obj = raw as Record<string, unknown>
  if (obj.version !== 1) return false
  if (!Array.isArray(obj.history) || !Array.isArray(obj.usage)) return false
  if (obj.history.length > MAX_HISTORY || obj.usage.length > MAX_USAGE) return false
  return Object.keys(obj).every(
    (key) => key === "version" || key === "history" || key === "usage",
  )
}
