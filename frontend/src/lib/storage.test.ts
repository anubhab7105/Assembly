import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { BrowserStorage, type HistoryRecord, StorageError } from "./storage"

const local = new Map<string, string>()

function setLocalStorage(options?: { blocked?: boolean; full?: boolean; failAt?: number }) {
  let writeCount = 0
  const storage = {
    getItem: (key: string) => {
      if (options?.blocked) throw new Error("localStorage blocked")
      return local.get(key) ?? null
    },
    setItem: (key: string, value: string) => {
      writeCount += 1
      if (options?.blocked) throw new Error("localStorage blocked")
      if (options?.full) throw new Error("quota exceeded")
      if (options?.failAt === writeCount) throw new Error("simulated one-off quota failure")
      local.set(key, value)
    },
    removeItem: (key: string) => {
      if (options?.blocked) throw new Error("localStorage blocked")
      local.delete(key)
    },
  } as Storage
  vi.stubGlobal("localStorage", storage)
  vi.stubGlobal("window", {
    get localStorage() {
      if (options?.blocked) throw new Error("localStorage blocked")
      return storage
    },
    ASSEMBLY_APP_MODE: "web",
  } as unknown as Window)
}

const baseRecord = {
  id: "run-1",
  question: "Which option is correct?",
  answer: "Option A.",
  status: "completed",
  created_at: "2026-10-15T10:00:00.000Z",
  minutes: 5,
}

describe("BrowserStorage lifecycle contracts", () => {
  beforeEach(() => {
    local.clear()
    vi.stubGlobal("indexedDB", undefined)
    setLocalStorage()
  })

  afterEach(() => vi.unstubAllGlobals())

  it("round-trips history and usage through export/import and a fresh instance", async () => {
    const original = new BrowserStorage()
    await original.saveHistory(baseRecord)
    await original.setUsage([{ provider: "groq", model: "m1", count: 3, tokens: 99 }])
    const backup = await original.exportJSON()

    const fresh = new BrowserStorage()
    await fresh.clearHistory()
    await fresh.setUsage([])
    await fresh.importJSON(backup)
    expect(await new BrowserStorage().getHistory("run-1")).toEqual(baseRecord)
    expect(await new BrowserStorage().getUsage()).toEqual([{ provider: "groq", model: "m1", count: 3, tokens: 99 }])
  })

  it("represents a fresh profile as empty and exports a complete versioned shape", async () => {
    const storage = new BrowserStorage()
    expect(await storage.listHistory()).toEqual([])
    expect(await storage.getHistory("missing")).toBeNull()
    expect(await storage.getUsage()).toEqual([])
    expect(JSON.parse(await storage.exportJSON())).toEqual({ version: 1, history: [], usage: [] })
  })

  it("falls back to localStorage when IndexedDB is unavailable", async () => {
    const storage = new BrowserStorage()
    await storage.saveHistory(baseRecord)
    expect(JSON.parse(local.get("assembly:history") ?? "null")).toEqual([baseRecord])
    expect(await new BrowserStorage().getHistory("run-1")).toEqual(baseRecord)
  })

  it("fails clearly rather than falsely claiming a save when both layers fail", async () => {
    setLocalStorage({ blocked: true })
    const storage = new BrowserStorage()
    await expect(storage.saveHistory(baseRecord)).rejects.toBeInstanceOf(StorageError)
    await expect(storage.setSetting("example", "value")).rejects.toThrow(/storage is unavailable or full/i)
    await expect(storage.clearHistory()).rejects.toBeInstanceOf(StorageError)
  })

  it("rejects malformed JSON and unsupported/incomplete exports without changing saved data", async () => {
    const storage = new BrowserStorage()
    await storage.saveHistory(baseRecord)
    await expect(storage.importJSON("{nope")).rejects.toThrow(/valid JSON/)
    await expect(storage.importJSON(JSON.stringify({ version: 2, history: [], usage: [] }))).rejects.toThrow(/Unsupported/)
    await expect(storage.importJSON(JSON.stringify({ version: 1, history: [] }))).rejects.toThrow(/history and usage arrays/)
    expect(await storage.listHistory()).toEqual([baseRecord])
  })

  it("rejects malformed records as a whole without changing existing history or usage", async () => {
    const storage = new BrowserStorage()
    await storage.saveHistory(baseRecord)
    const existingUsage = [{ provider: "groq", model: "m1", count: 3, tokens: 10 }]
    await storage.setUsage(existingUsage)
    await expect(storage.importJSON(JSON.stringify({
      version: 1,
      history: [
        { ...baseRecord, id: "run-2" },
        { ...baseRecord, id: "", answer: "malformed" },
      ],
      usage: [{ provider: "", model: "broken", count: 0, tokens: 0 }],
    }))).rejects.toThrow(/invalid history record at row 2/i)
    expect(await storage.listHistory()).toEqual([baseRecord])
    expect(await storage.getUsage()).toEqual(existingUsage)
  })

  it("keeps the first duplicate valid history id and merges duplicate usage conservatively", async () => {
    const storage = new BrowserStorage()
    await storage.importJSON(JSON.stringify({
      version: 1,
      history: [
        baseRecord,
        { ...baseRecord, answer: "duplicate should be ignored" },
      ],
      usage: [
        { provider: "groq", model: "m1", count: 3, tokens: 10 },
        { provider: "groq", model: "m1", count: 4, tokens: 9 },
      ],
    }))
    expect(await storage.listHistory()).toEqual([baseRecord])
    expect(await storage.getUsage()).toEqual([{ provider: "groq", model: "m1", count: 4, tokens: 10 }])
  })

  it("rolls back a partial localStorage import when writing usage fails", async () => {
    const storage = new BrowserStorage()
    await storage.saveHistory(baseRecord)
    const existingUsage = [{ provider: "groq", model: "m1", count: 2, tokens: 20 }]
    await storage.setUsage(existingUsage)
    const incoming = JSON.stringify({
      version: 1,
      history: [{ ...baseRecord, id: "imported" }],
      usage: [{ provider: "gemini", model: "m2", count: 7, tokens: 70 }],
    })

    // Simulate the second write failing after the history write succeeds.
    // The one-shot failure still allows rollback writes to complete.
    setLocalStorage({ failAt: 2 })
    await expect(storage.importJSON(incoming)).rejects.toBeInstanceOf(StorageError)
    expect(await storage.listHistory()).toEqual([baseRecord])
    expect(await storage.getUsage()).toEqual(existingUsage)

    // The one-shot storage failure is gone, so the same valid backup can be
    // retried without clearing or recreating the existing local history.
    await storage.importJSON(incoming)
    expect((await storage.listHistory()).map((record) => record.id).sort()).toEqual(["imported", "run-1"])
    expect(await storage.getUsage()).toEqual([
      { provider: "groq", model: "m1", count: 2, tokens: 20 },
      { provider: "gemini", model: "m2", count: 7, tokens: 70 },
    ])
  })

  it("merges imports without deleting unrelated local history and is idempotent", async () => {
    const storage = new BrowserStorage()
    await storage.saveHistory({ ...baseRecord, id: "existing" })
    await storage.importJSON(JSON.stringify({
      version: 1,
      history: [{ ...baseRecord, id: "imported" }],
      usage: [],
    }))
    await storage.importJSON(JSON.stringify({
      version: 1,
      history: [{ ...baseRecord, id: "imported" }],
      usage: [],
    }))
    const ids = (await storage.listHistory()).map((item) => item.id).sort()
    expect(ids).toEqual(["existing", "imported"])
  })

  it("does not read a false empty state or report delete success when both stores fail", async () => {
    const storage = new BrowserStorage()
    setLocalStorage({ blocked: true })
    await expect(storage.listHistory()).rejects.toBeInstanceOf(StorageError)
    await expect(storage.deleteHistory("run-1")).rejects.toBeInstanceOf(StorageError)
  })

  it("surfaces localStorage quota exhaustion if IndexedDB is unavailable", async () => {
    const storage = new BrowserStorage()
    setLocalStorage({ full: true })
    await expect(storage.setSetting("example", "value")).rejects.toBeInstanceOf(StorageError)
  })

  it("round-trips only attachment metadata, never uploaded content", async () => {
    const store = new BrowserStorage()
    const contentCanary = "ATTACHMENT-CONTENT-MUST-NOT-BE-PERSISTED"
    await store.importJSON(JSON.stringify({
      version: 1,
      history: [{
        ...baseRecord,
        attachments: [{
          filename: "analysis.txt",
          media_type: "text/plain",
          size_bytes: 50,
          content: contentCanary,
        }],
      }],
      usage: [],
    }))
    const loaded = await new BrowserStorage().getHistory("run-1")
    expect(loaded?.attachments).toEqual([
      { filename: "analysis.txt", media_type: "text/plain", size_bytes: 50 },
    ])
    const backup = await new BrowserStorage().exportJSON()
    expect(backup).not.toContain(contentCanary)
    expect(backup).not.toContain('"content"')
  })

  it("drops invalid attachment metadata when importing history", async () => {
    const store = new BrowserStorage()
    await store.importJSON(JSON.stringify({
      version: 1,
      history: [{
        ...baseRecord,
        attachments: [{ filename: "../unsafe.txt", media_type: "text/plain", size_bytes: 25 }],
      }],
      usage: [],
    }))
    expect((await store.getHistory("run-1"))?.attachments).toBeUndefined()
  })

  it("preserves metadata for more than five attachments and files up to 10 MiB (50 MiB total)", async () => {
    const store = new BrowserStorage()
    const eightMiB = 8 * 1024 * 1024
    const attachments = [
      { filename: "empty.txt", media_type: "text/plain", size_bytes: 0 },
      ...Array.from({ length: 6 }, (_, i) => ({
        filename: `part-${i}.txt`,
        media_type: "text/plain",
        size_bytes: eightMiB,
      })),
    ]
    await store.saveHistory({ ...baseRecord, id: "run-7-files", attachments })
    const saved = await store.getHistory("run-7-files")
    expect(saved?.attachments).toEqual(attachments)

    // Drops attachment metadata arrays that exceed 10 MiB per file or 50 MiB total.
    await store.saveHistory({
      ...baseRecord,
      id: "run-over-10",
      attachments: [{ filename: "too-big.txt", media_type: "text/plain", size_bytes: 10 * 1024 * 1024 + 1 }],
    })
    expect((await store.getHistory("run-over-10"))?.attachments).toBeUndefined()

    await store.saveHistory({
      ...baseRecord,
      id: "run-over-50",
      attachments: Array.from({ length: 6 }, (_, i) => ({
        filename: `nine-${i}.txt`,
        media_type: "text/plain",
        size_bytes: 9 * 1024 * 1024,
      })),
    })
    expect((await store.getHistory("run-over-50"))?.attachments).toBeUndefined()
  })

  it("enforces consistent answer, export, and import size contracts", async () => {
    const store = new BrowserStorage()

    // 1. saveHistory rejects records exceeding MAX_ANSWER_CHARS (250,000 chars)
    await expect(
      store.saveHistory({
        ...baseRecord,
        id: "too-long",
        answer: "a".repeat(250_001),
      }),
    ).rejects.toThrow(/exceeds maximum allowed length/)

    // 2. importJSON rejects backups exceeding MAX_BACKUP_IMPORT_BYTES (50 MiB)
    const overFiftyMiB = JSON.stringify({
      version: 1,
      history: [],
      usage: [],
      padding: "x".repeat(50 * 1024 * 1024 + 1),
    })
    await expect(store.importJSON(overFiftyMiB)).rejects.toThrow(/Maximum allowed backup size is 50 MiB/)

    // 3. saveHistory rejects when resulting persisted history exceeds MAX_BACKUP_EXPORT_BYTES (50 MiB)
    // 72 records of 240,000 '€' chars (720,000 UTF-8 bytes each) = ~51.84 MB (under 52,428,800 bytes)
    const largeValidRecords = Array.from({ length: 72 }, (_, i) => ({
      ...baseRecord,
      id: `saved-${i}`,
      answer: "€".repeat(240_000),
    }))
    local.set("assembly:history", JSON.stringify(largeValidRecords))

    // A 73rd record pushes total serialized backup size over 50 MiB
    await expect(
      store.saveHistory({
        ...baseRecord,
        id: "overflow-record",
        answer: "€".repeat(240_000),
      }),
    ).rejects.toThrow(/History exceeds maximum backup storage limit of 50 MiB\. Nothing was saved\./)

    // Existing history remains unchanged, and the rejected record was not saved
    expect(await store.getHistory("overflow-record")).toBeNull()
    const preserved = await store.listHistory()
    expect(preserved.length).toBe(72)
    expect(preserved[0].id).toBe("saved-0")
  })

  it("enforces the 5 MiB limit on external imports while allowing export and restore of valid > 5 MiB Assembly v1 backups", async () => {
    const store = new BrowserStorage()
    await store.saveHistory(baseRecord)

    // External non-backup > 5 MiB is rejected before updating storage.
    const utf8Over5MiBExternal = JSON.stringify({
      version: 1,
      external_source: true,
      history: [{ ...baseRecord, id: "oversized", answer: "x".repeat(100_000) }],
      usage: [],
      extra_payload: "p".repeat(5 * 1024 * 1024 + 1024),
    })
    await expect(store.importJSON(utf8Over5MiBExternal)).rejects.toThrow(/5 MiB/)
    expect(await store.listHistory()).toEqual([baseRecord])

    // Large valid histories (> 5 MiB UTF-8 bytes) within MAX_ANSWER_CHARS still export cleanly and restore.
    for (let i = 0; i < 24; i += 1) {
      await store.saveHistory({
        ...baseRecord,
        id: `big-${i}`,
        answer: "x".repeat(240_000),
      })
    }
    const backup = await store.exportJSON()
    expect(new TextEncoder().encode(backup).byteLength).toBeGreaterThan(5 * 1024 * 1024)

    await store.clearHistory()
    expect(await store.listHistory()).toEqual([])

    await store.importJSON(backup)
    expect((await store.listHistory()).length).toBe(25)
  })

  it("preserves oversized legacy records so they remain visible, exportable, and not lost during saves, deletions, or imports", async () => {
    const store = new BrowserStorage()

    // 1. Seed an oversized legacy record that exceeds MAX_ANSWER_CHARS (250,000) and MAX_QUESTION_CHARS (4,000)
    const legacyRecord: HistoryRecord = {
      ...baseRecord,
      id: "legacy-oversized",
      question: "Q".repeat(4_500),
      answer: "A".repeat(260_000),
    }
    local.set("assembly:history", JSON.stringify([legacyRecord]))

    // 2. Reading history returns the oversized legacy record
    const historyBefore = await store.listHistory()
    expect(historyBefore).toHaveLength(1)
    expect(historyBefore[0].id).toBe("legacy-oversized")
    expect(await store.getHistory("legacy-oversized")).toEqual(legacyRecord)

    // 3. Export preserves the oversized legacy record in a restorable backup
    const exported = await store.exportJSON()
    expect(exported).toContain("legacy-oversized")

    // 4. Modifying history: saving a new record preserves the legacy record
    const newRecord: HistoryRecord = {
      ...baseRecord,
      id: "new-record-1",
      question: "Normal question?",
      answer: "Normal answer.",
    }
    await store.saveHistory(newRecord)
    const historyAfterSave = await store.listHistory()
    expect(historyAfterSave).toHaveLength(2)
    expect(await store.getHistory("legacy-oversized")).toEqual(legacyRecord)
    expect(await store.getHistory("new-record-1")).toEqual(newRecord)

    // 5. Modifying history: deleting the new record does not lose the legacy record
    await store.deleteHistory("new-record-1")
    const historyAfterDelete = await store.listHistory()
    expect(historyAfterDelete).toHaveLength(1)
    expect(historyAfterDelete[0].id).toBe("legacy-oversized")

    // 6. Modifying history: importing a backup restores and preserves the legacy record
    await store.clearHistory()
    expect(await store.listHistory()).toEqual([])
    await store.importJSON(exported)
    expect(await store.getHistory("legacy-oversized")).toEqual(legacyRecord)

    // 7. Incoming oversized records remain rejected on saveHistory
    await expect(
      store.saveHistory({
        ...baseRecord,
        id: "rejected-incoming",
        answer: "X".repeat(250_001),
      }),
    ).rejects.toThrow(/exceeds maximum allowed length/)
    expect(await store.getHistory("rejected-incoming")).toBeNull()
    expect(await store.getHistory("legacy-oversized")).toEqual(legacyRecord)
  })
})
