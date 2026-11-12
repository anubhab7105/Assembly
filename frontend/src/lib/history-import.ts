import {
  MAX_BACKUP_IMPORT_BYTES,
  MAX_HISTORY_FILE_SIZE,
} from "./history-file-limits"

export const MAX_IMPORT_FILE_SIZE = MAX_HISTORY_FILE_SIZE

type ImportFile = Pick<File, "size" | "text"> & {
  slice?: (start?: number, end?: number) => Pick<Blob, "text">
}

const ASSEMBLY_BACKUP_PREFIX_RE = /^\{\s*"version"\s*:\s*1\s*,\s*"history"\s*:\s*\[/

/**
 * Imports a history file after checking its size.
 * Oversized non-backup files are rejected before their contents are read,
 * while bounded valid Assembly version-1 backups pass through for full validation.
 */
export async function importHistoryFile(
  file: ImportFile,
  importJSON: (text: string) => Promise<unknown>
): Promise<void> {
  if (file.size > MAX_BACKUP_IMPORT_BYTES) {
    throw new Error(
      "This backup is too large to import. Maximum allowed backup size is 50 MiB. Your existing history was not changed."
    )
  }

  if (file.size > MAX_IMPORT_FILE_SIZE) {
    if (typeof file.slice === "function") {
      const head = await file.slice(0, 256).text()
      if (!ASSEMBLY_BACKUP_PREFIX_RE.test(head)) {
        throw new Error(
          "This file is too large to import. Maximum allowed size is 5 MiB. Your existing history was not changed."
        )
      }
    } else {
      throw new Error(
        "This file is too large to import. Maximum allowed size is 5 MiB. Your existing history was not changed."
      )
    }
  }

  const text = await file.text()
  await importJSON(text)
}