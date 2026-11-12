/** Maximum allowed size for external/untrusted history import files (5 MiB). */
export const MAX_HISTORY_FILE_SIZE = 5 * 1024 * 1024

/** Maximum number of history entries retained and accepted in Assembly v1 backups. */
export const MAX_HISTORY = 200

/** Maximum number of usage entries retained and accepted in Assembly v1 backups. */
export const MAX_USAGE = 200

/**
 * Hard OOM guard when restoring Assembly version-1 backups (256 MiB).
 * Covers large valid saveHistory() exports (up to 200 records with uncapped
 * answer text) while remaining safely below JS string/IndexedDB limits.
 */
export const MAX_BACKUP_IMPORT_BYTES = 256 * 1024 * 1024

/** Human-readable MiB value for MAX_BACKUP_IMPORT_BYTES error messages. */
export const MAX_BACKUP_IMPORT_MIB = Math.round(MAX_BACKUP_IMPORT_BYTES / (1024 * 1024))

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
