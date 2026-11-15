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

const TOO_LARGE_EXTERNAL_MSG =
  "This file is too large to import. Maximum allowed size is 5 MiB. Your existing history was not changed."

function extractTopLevelKeys(snippet: string): string[] {
  const keys: string[] = []
  const re = /"([a-zA-Z0-9_-]+)"\s*:/g
  let match: RegExpExecArray | null
  while ((match = re.exec(snippet)) !== null) {
    keys.push(match[1])
  }
  return keys
}

async function passesBackupPreflight(file: ImportFile): Promise<boolean> {
  if (typeof file.slice !== "function") return false
  const head = await file.slice(0, PREFLIGHT_SLICE_BYTES).text()
  if (!head.trimStart().startsWith("{")) return false

  const tailStart = Math.max(0, file.size - PREFLIGHT_SLICE_BYTES)
  const tail = await file.slice(tailStart, file.size).text()
  if (!tail.trimEnd().endsWith("}")) return false

  const hasVersion1 = /"version"\s*:\s*1\b/.test(head) || /"version"\s*:\s*1\b/.test(tail)
  const hasHistoryArray = /"history"\s*:\s*\[/.test(head) || /"history"\s*:\s*\[/.test(tail)
  const hasUsageArray = /"usage"\s*:\s*\[/.test(head) || /"usage"\s*:\s*\[/.test(tail)
  if (!hasVersion1 || !hasHistoryArray || !hasUsageArray) return false

  // An empty history array cannot legitimately produce a backup > 5 MiB.
  if (/"history"\s*:\s*\[\s*\]/.test(head) || /"history"\s*:\s*\[\s*\]/.test(tail)) {
    return false
  }

  // Reject any top-level key that is not version, history, or usage.
  const headPrefix = head.split(/"history"\s*:\s*\[/)[0]
  for (const key of extractTopLevelKeys(headPrefix)) {
    if (key !== "version" && key !== "history" && key !== "usage") return false
  }

  const lastBracketIndex = tail.lastIndexOf("]")
  if (lastBracketIndex !== -1) {
    const tailSuffix = tail.slice(lastBracketIndex + 1)
    for (const key of extractTopLevelKeys(tailSuffix)) {
      if (key !== "version" && key !== "history" && key !== "usage") return false
    }
  }

  const tailClosing = tail.trimEnd()
  const validTailEnd =
    /\}(?:\s*\])?\s*,?\s*"(?:usage|version)"\s*:\s*(?:\[[^\]]*\]|1)\s*\}$/.test(tailClosing) ||
    /\}\s*\]\s*\}$/.test(tailClosing)
  if (!validTailEnd) {
    return false
  }

  return true
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