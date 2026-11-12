import { describe, expect, it, vi } from "vitest"
import {
  MAX_ATTACHMENT_CONTEXT_CHARS,
  MAX_ATTACHMENT_FILE_BYTES,
  MAX_ATTACHMENT_TOTAL_BYTES,
  calculateAttachmentsTotalBytes,
  estimateAttachmentContextChars,
  validateAttachmentBatch,
  type DraftAttachment,
  type PickedAttachmentFile,
} from "./attachments"

const MiB = 1024 * 1024

function makeMockFile(
  name: string,
  size: number,
  content = "sample",
  type = "text/plain",
): PickedAttachmentFile & { text: ReturnType<typeof vi.fn> } {
  return {
    name,
    size,
    type,
    text: vi.fn().mockResolvedValue(content),
  }
}

describe("Frontend attachment limits and batch validation", () => {
  it("enforces exact 10 MiB and 50 MiB byte constants", () => {
    expect(MAX_ATTACHMENT_FILE_BYTES).toBe(10 * 1024 * 1024)
    expect(MAX_ATTACHMENT_TOTAL_BYTES).toBe(50 * 1024 * 1024)
  })

  it("accepts empty 0-byte, 2 MiB, 8 MiB, and exact 10 MiB files without minimum size restrictions", async () => {
    const emptyFile = makeMockFile("empty.txt", 0, "")
    const twoMiB = makeMockFile("two.md", 2 * MiB, "# Notes")
    const eightMiB = makeMockFile("eight.log", 8 * MiB, "INFO ok")
    const exactTenMiB = makeMockFile("ten.txt", MAX_ATTACHMENT_FILE_BYTES, "payload")

    const result = await validateAttachmentBatch([], [
      emptyFile,
      twoMiB,
      eightMiB,
      exactTenMiB,
    ])

    expect(result.errors).toEqual([])
    expect(result.accepted.map((a) => a.filename)).toEqual([
      "empty.txt",
      "two.md",
      "eight.log",
      "ten.txt",
    ])
    expect(result.accepted[0].size).toBe(0)
    expect(result.totalBytes).toBe(20 * MiB)
  })

  it("rejects files over 10 MiB before reading their contents", async () => {
    const slightlyOver = makeMockFile("slightly-over.txt", MAX_ATTACHMENT_FILE_BYTES + 1, "secret")
    const halfMiBOver = makeMockFile("large.txt", 10.5 * MiB, "secret")

    const result = await validateAttachmentBatch([], [slightlyOver, halfMiBOver])

    expect(result.accepted).toEqual([])
    expect(result.errors).toEqual([
      "slightly-over.txt: file exceeds the 10 MiB per-file limit.",
      "large.txt: file exceeds the 10 MiB per-file limit.",
    ])
    expect(slightlyOver.text).not.toHaveBeenCalled()
    expect(halfMiBOver.text).not.toHaveBeenCalled()
  })

  it("allows more than five attachments and accepts up to 50 MiB total (5 x 10 MiB and 6 x 8 MiB)", async () => {
    const fiveTen = Array.from({ length: 5 }, (_, i) =>
      makeMockFile(`ten-${i}.txt`, MAX_ATTACHMENT_FILE_BYTES, "x"),
    )
    const exact50 = await validateAttachmentBatch([], fiveTen)
    expect(exact50.errors).toEqual([])
    expect(exact50.accepted).toHaveLength(5)
    expect(exact50.totalBytes).toBe(50 * MiB)

    const sixEight = Array.from({ length: 6 }, (_, i) =>
      makeMockFile(`eight-${i}.txt`, 8 * MiB, "y"),
    )
    const exact48 = await validateAttachmentBatch([], sixEight)
    expect(exact48.errors).toEqual([])
    expect(exact48.accepted).toHaveLength(6)
    expect(exact48.totalBytes).toBe(48 * MiB)
  })

  it("rejects uploads exceeding 50 MiB (6 x 9 MiB) before reading the overflow file", async () => {
    const sixNine = Array.from({ length: 6 }, (_, i) =>
      makeMockFile(`nine-${i}.txt`, 9 * MiB, "z"),
    )

    const result = await validateAttachmentBatch([], sixNine)

    expect(result.accepted).toHaveLength(5)
    expect(result.totalBytes).toBe(45 * MiB)
    expect(result.errors).toEqual(["Attachments exceed the 50 MiB combined limit."])
    expect(sixNine[4].text).toHaveBeenCalledOnce()
    expect(sixNine[5].text).not.toHaveBeenCalled()
  })

  it("includes existing attachments across multiple batches without double-counting", async () => {
    const batch1 = await validateAttachmentBatch([], [
      makeMockFile("a.txt", 8 * MiB),
      makeMockFile("b.txt", 8 * MiB),
      makeMockFile("c.txt", 8 * MiB),
    ])
    expect(batch1.totalBytes).toBe(24 * MiB)

    const batch2 = await validateAttachmentBatch(batch1.accepted, [
      makeMockFile("d.txt", 10 * MiB),
      makeMockFile("e.txt", 10 * MiB),
      makeMockFile("f.txt", 6 * MiB),
    ])
    expect(batch2.errors).toEqual([])
    expect(batch2.accepted).toHaveLength(3)
    const allSix: DraftAttachment[] = [...batch1.accepted, ...batch2.accepted]
    expect(calculateAttachmentsTotalBytes(allSix)).toBe(50 * MiB)
    expect(batch2.totalBytes).toBe(50 * MiB)

    const overflowFile = makeMockFile("one-too-much.txt", 1, "a")
    const batch3 = await validateAttachmentBatch(allSix, [overflowFile])
    expect(batch3.accepted).toEqual([])
    expect(batch3.errors).toEqual(["Attachments exceed the 50 MiB combined limit."])
    expect(overflowFile.text).not.toHaveBeenCalled()
  })

  it("checks unsupported types, invalid JSON, and control characters accurately", async () => {
    const exe = makeMockFile("payload.exe", 100, "bin")
    const badJson = makeMockFile("broken.json", 10, "{invalid", "application/json")
    const binaryCtrl = makeMockFile("nullbyte.txt", 10, "ok\u0000bad")

    const result = await validateAttachmentBatch([], [exe, badJson, binaryCtrl])

    expect(result.accepted).toEqual([])
    expect(exe.text).not.toHaveBeenCalled()
    expect(result.errors).toEqual([
      "payload.exe: unsupported type. Choose a text, Markdown, CSV, JSON, log, or source/configuration file.",
      "broken.json: invalid JSON.",
      "nullbyte.txt: binary or unsupported control characters aren't supported.",
    ])
  })

  it("uses UTF-8 byte length after read and does not leak failed file bytes into total", async () => {
    const multiByteOverTenMiB = makeMockFile(
      "multibyte.txt",
      5 * MiB + 1,
      "é".repeat(5 * MiB + 1),
    )
    const validAfterFailure = makeMockFile("ok.txt", 2 * MiB, "valid")

    const result = await validateAttachmentBatch([], [multiByteOverTenMiB, validAfterFailure])

    expect(result.accepted.map((a) => a.filename)).toEqual(["ok.txt"])
    expect(result.totalBytes).toBe(2 * MiB)
    expect(result.errors).toEqual(["multibyte.txt: file exceeds the 10 MiB per-file limit."])
  })

  it("estimates formatted prompt chars including headers, wrappers, separators, and delimiter escaping", () => {
    expect(estimateAttachmentContextChars([])).toBe(0)

    // Raw text is under 24,000 chars, but per-file wrappers + separators push
    // the formatted prompt context over MAX_ATTACHMENT_CONTEXT_CHARS.
    const nearBudgetFiles: DraftAttachment[] = Array.from({ length: 10 }, (_, i) => ({
      id: `id-${i}`,
      filename: `notes-${i}.txt`,
      media_type: "text/plain",
      content: "a".repeat(2350),
      size: 2350,
    }))
    const rawLength = nearBudgetFiles.reduce((sum, f) => sum + f.content.length, 0)
    expect(rawLength).toBe(23_500)
    expect(rawLength).toBeLessThan(MAX_ATTACHMENT_CONTEXT_CHARS)
    expect(estimateAttachmentContextChars(nearBudgetFiles)).toBeGreaterThan(
      MAX_ATTACHMENT_CONTEXT_CHARS,
    )
  })
})

