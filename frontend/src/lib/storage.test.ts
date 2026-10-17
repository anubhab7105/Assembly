import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { BrowserStorage, StorageError } from "./storage"

const local = new Map<string, string>()

function setLocalStorage(options?: { blocked?: boolean; full?: boolean }) {
  const storage = {
    getItem: (key: string) => {
      if (options?.blocked) throw new Error("localStorage blocked")
      return local.get(key) ?? null
    },
    setItem: (key: string, value: string) => {
      if (options?.blocked) throw new Error("localStorage blocked")
      if (options?.full) throw new Error("quota exceeded")
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

  it("skips malformed records and keeps the first duplicate history id", async () => {
    const storage = new BrowserStorage()
    await storage.importJSON(JSON.stringify({
      version: 1,
      history: [
        baseRecord,
        { ...baseRecord, answer: "duplicate should be ignored" },
        { ...baseRecord, id: "", answer: "malformed" },
        { ...baseRecord, id: "run-2", minutes: "five" },
      ],
      usage: [
        { provider: "groq", model: "m1", count: 3, tokens: 10 },
        { provider: "groq", model: "m1", count: 4, tokens: 9 },
        { provider: "", model: "broken", count: 0, tokens: 0 },
      ],
    }))
    expect(await storage.listHistory()).toEqual([baseRecord])
    expect(await storage.getUsage()).toEqual([{ provider: "groq", model: "m1", count: 4, tokens: 10 }])
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
