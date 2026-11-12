import { MAX_HISTORY_FILE_SIZE } from "./history-file-limits"

export const MAX_IMPORT_FILE_SIZE = MAX_HISTORY_FILE_SIZE

type ImportFile = Pick<File, "size" | "text">

/**
 * Imports a history file after checking its size.
 * Oversized files are rejected before their contents are read.
 */
export async function importHistoryFile(
  file: ImportFile,
  importJSON: (text: string) => Promise<unknown>
): Promise<void> {
  if (file.size > MAX_IMPORT_FILE_SIZE) {
    throw new Error(
      "This file is too large to import. Maximum allowed size is 5 MiB. Your existing history was not changed."
    )
  }

  const text = await file.text()
  await importJSON(text)
}