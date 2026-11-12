export const MAX_ATTACHMENT_FILE_BYTES = 10 * 1024 * 1024
export const MAX_ATTACHMENT_TOTAL_BYTES = 50 * 1024 * 1024
export const MAX_ATTACHMENT_COUNT = 100
export const MAX_ATTACHMENT_CONTEXT_CHARS = 24_000

export const SUPPORTED_ATTACHMENT_EXTENSIONS = new Set([
  "txt", "md", "csv", "json", "log", "py", "js", "jsx", "ts", "tsx",
  "html", "css", "yml", "yaml", "toml", "ini", "cfg", "conf", "xml",
  "sql", "sh", "ps1", "bat", "env.example",
])

export type DraftAttachment = {
  id: string
  filename: string
  media_type: string
  content: string
  size: number
}

export type PickedAttachmentFile = Pick<File, "name" | "size" | "type" | "text">

export type AttachmentBatchResult = {
  accepted: DraftAttachment[]
  errors: string[]
  totalBytes: number
}

export function getAttachmentExtension(filename: string): string {
  const lower = filename.toLowerCase()
  return lower.endsWith(".env.example")
    ? "env.example"
    : lower.includes(".")
      ? lower.split(".").pop() ?? ""
      : ""
}

export function calculateAttachmentsTotalBytes(
  attachments: ReadonlyArray<Pick<DraftAttachment, "size">>,
): number {
  return attachments.reduce(
    (sum, item) => sum + (Number.isFinite(item.size) && item.size > 0 ? item.size : 0),
    0,
  )
}

function hasUnsupportedControlChars(text: string): boolean {
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i)
    if ((code < 32 && code !== 9 && code !== 10 && code !== 12 && code !== 13) || code === 127) {
      return true
    }
  }
  return false
}

export async function validateAttachmentBatch(
  existingAttachments: ReadonlyArray<DraftAttachment>,
  pickedFiles: ReadonlyArray<PickedAttachmentFile>,
): Promise<AttachmentBatchResult> {
  let totalBytes = calculateAttachmentsTotalBytes(existingAttachments)
  let currentCount = existingAttachments.length
  const accepted: DraftAttachment[] = []
  const errors: string[] = []
  const pushError = (message: string) => {
    if (!errors.includes(message)) {
      errors.push(message)
    }
  }
  const encoder = new TextEncoder()

  for (const file of pickedFiles) {
    if (currentCount >= MAX_ATTACHMENT_COUNT) {
      pushError(`Attachments exceed the ${MAX_ATTACHMENT_COUNT}-file per-investigation limit.`)
      continue
    }

    const extension = getAttachmentExtension(file.name)
    if (!SUPPORTED_ATTACHMENT_EXTENSIONS.has(extension)) {
      pushError(
        `${file.name}: unsupported type. Choose a text, Markdown, CSV, JSON, log, or source/configuration file.`,
      )
      continue
    }

    if (!Number.isFinite(file.size) || file.size < 0) {
      pushError(`${file.name}: invalid file size.`)
      continue
    }

    if (file.size > MAX_ATTACHMENT_FILE_BYTES) {
      pushError(`${file.name}: file exceeds the 10 MiB per-file limit.`)
      continue
    }

    if (totalBytes + file.size > MAX_ATTACHMENT_TOTAL_BYTES) {
      pushError("Attachments exceed the 50 MiB combined limit.")
      continue
    }

    try {
      const content = await file.text()
      const utf8Bytes = encoder.encode(content).byteLength
      const effectiveSize = Math.max(file.size, utf8Bytes)

      if (effectiveSize > MAX_ATTACHMENT_FILE_BYTES) {
        pushError(`${file.name}: file exceeds the 10 MiB per-file limit.`)
        continue
      }

      if (totalBytes + effectiveSize > MAX_ATTACHMENT_TOTAL_BYTES) {
        pushError("Attachments exceed the 50 MiB combined limit.")
        continue
      }

      if (hasUnsupportedControlChars(content)) {
        pushError(`${file.name}: binary or unsupported control characters aren't supported.`)
        continue
      }

      if (extension === "json") {
        try {
          JSON.parse(content)
        } catch {
          pushError(`${file.name}: invalid JSON.`)
          continue
        }
      }

      totalBytes += effectiveSize
      currentCount += 1
      accepted.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}-${accepted.length}`,
        filename: file.name,
        media_type: file.type || "text/plain",
        content,
        size: effectiveSize,
      })
    } catch {
      pushError(`${file.name}: couldn't read this file.`)
    }
  }

  return { accepted, errors, totalBytes }
}

