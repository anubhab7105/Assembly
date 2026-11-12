import {
  isAssemblyBackupEnvelope,
  MAX_BACKUP_IMPORT_BYTES,
  MAX_BACKUP_IMPORT_MIB,
  MAX_HISTORY_FILE_SIZE,
} from "./history-file-limits"

export const MAX_IMPORT_FILE_SIZE = MAX_HISTORY_FILE_SIZE

type ImportFile = Pick<File, "size" | "text"> & {
  slice?: (start?: number, end?: number) => Pick<Blob, "text">
}

const PREFLIGHT_SLICE_BYTES = 128 * 1024
const ASSEMBLY_BACKUP_START_RE = /^\{\s*"(?:version|history|usage)"\s*:/
const ASSEMBLY_BACKUP_VERSION_RE = /"version"\s*:\s*1(?:\s*,|\s*\})/

const TOO_LARGE_EXTERNAL_MSG =
  "This file is too large to import. Maximum allowed size is 5 MiB. Your existing history was not changed."

async function passesBackupPreflight(file: ImportFile): Promise<boolean> {
  if (typeof file.slice !== "function") return false
  const head = await file.slice(0, PREFLIGHT_SLICE_BYTES).text()
  if (!ASSEMBLY_BACKUP_START_RE.test(head)) return false
  if (ASSEMBLY_BACKUP_VERSION_RE.test(head)) return true
  if (file.size <= PREFLIGHT_SLICE_BYTES) return false
  const tailStart = Math.max(0, file.size - PREFLIGHT_SLICE_BYTES)
  const tail = await file.slice(tailStart, file.size).text()
  return ASSEMBLY_BACKUP_VERSION_RE.test(tail)
}

/**
 * Imports a history file after checking its size.
 * Oversized non-backup files are rejected before reading their full contents,
 * while files passing bounded preflight are fully validated as Assembly
 * version-1 backup envelopes before invoking `importJSON`.
 */
export async function importHistoryFile(
  file: ImportFile,
  importJSON: (text: string) => Promise<unknown>
): Promise<void> {
  if (file.size > MAX_BACKUP_IMPORT_BYTES) {
    throw new Error(
      `This backup is too large to import. Maximum allowed backup size is ${MAX_BACKUP_IMPORT_MIB} MiB. Your existing history was not changed.`
    )
  }

  const isLargeFile = file.size > MAX_IMPORT_FILE_SIZE
  if (isLargeFile && !(await passesBackupPreflight(file))) {
    throw new Error(TOO_LARGE_EXTERNAL_MSG)
  }

  const text = await file.text()
  if (isLargeFile) {
    let raw: unknown
    try {
      raw = JSON.parse(text)
    } catch {
      throw new Error(TOO_LARGE_EXTERNAL_MSG)
    }
    if (!isAssemblyBackupEnvelope(raw)) {
      throw new Error(TOO_LARGE_EXTERNAL_MSG)
    }
  }

  await importJSON(text)
}