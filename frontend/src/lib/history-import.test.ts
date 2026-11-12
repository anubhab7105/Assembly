import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  importHistoryFile,
  MAX_IMPORT_FILE_SIZE,
} from "./history-import"
import { BrowserStorage, type HistoryRecord } from "./storage"

function setupBrowserStorageGlobals(): void {
  const store = new Map<string, string>()
  const localStorageMock: Storage = {
    get length() {
      return store.size
    },
    clear: () => store.clear(),
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => [...store.keys()][index] ?? null,
    removeItem: (key: string) => {
      store.delete(key)
    },
    setItem: (key: string, value: string) => {
      store.set(key, value)
    },
  }
  vi.stubGlobal("indexedDB", undefined)
  vi.stubGlobal("localStorage", localStorageMock)
  vi.stubGlobal("window", { localStorage: localStorageMock })
}

function makeByteBackedFile(content: string) {
  const blob = new Blob([content], { type: "application/json" })
  const textSpy = vi.fn(() => blob.text())
  return {
    size: blob.size,
    slice: (start?: number, end?: number) => blob.slice(start, end),
    text: textSpy,
  }
}

describe("History import file size validation", () => {
  beforeEach(() => {
    setupBrowserStorageGlobals()
  })

  it("allows a 4 MiB file", async () => {
    const file = {
      size: 4 * 1024 * 1024,
      text: vi.fn().mockResolvedValue("{}"),
    }

    const importJSON = vi.fn().mockResolvedValue(undefined)

    await importHistoryFile(file, importJSON)

    expect(file.text).toHaveBeenCalledOnce()
    expect(importJSON).toHaveBeenCalledWith("{}")
  })

  it("allows a file exactly 5 MiB", async () => {
    const file = {
      size: MAX_IMPORT_FILE_SIZE,
      text: vi.fn().mockResolvedValue("{}"),
    }

    const importJSON = vi.fn().mockResolvedValue(undefined)

    await importHistoryFile(file, importJSON)

    expect(file.text).toHaveBeenCalledOnce()
    expect(importJSON).toHaveBeenCalledWith("{}")
  })

  it("rejects a file larger than 5 MiB before reading it", async () => {
    const file = {
      size: 6 * 1024 * 1024,
      text: vi.fn().mockResolvedValue("{}"),
    }

    const importJSON = vi.fn().mockResolvedValue(undefined)

    await expect(
      importHistoryFile(file, importJSON)
    ).rejects.toThrow(
      "This file is too large to import."
    )

    expect(file.text).not.toHaveBeenCalled()
    expect(importJSON).not.toHaveBeenCalled()
  })

  it("restores > 5 MiB valid Assembly backups regardless of key order and rejects oversized non-backups", async () => {
    const storage = new BrowserStorage()
    const baseRecord: HistoryRecord = {
      id: "run-0",
      question: "Test question?",
      answer: "x".repeat(900_000),
      status: "completed",
      created_at: "2026-01-01T00:00:00.000Z",
      minutes: 5,
    }
    for (let i = 0; i < 6; i += 1) {
      await storage.saveHistory({ ...baseRecord, id: `big-${i}` })
    }
    await storage.setUsage([{ provider: "google", model: "gemini", count: 2, tokens: 1200 }])

    const exportedPayload = await storage.exportJSON()
    const exportedFile = makeByteBackedFile(exportedPayload)
    expect(exportedFile.size).toBeGreaterThan(MAX_IMPORT_FILE_SIZE)

    await storage.clearHistory()
    await storage.setUsage([])

    const importSpy = vi.spyOn(storage, "importJSON")
    await importHistoryFile(exportedFile, (text) => storage.importJSON(text))

    expect(exportedFile.text).toHaveBeenCalledOnce()
    expect(importSpy).toHaveBeenCalledWith(exportedPayload)
    expect(await storage.listHistory()).toHaveLength(6)
    expect(await storage.getUsage()).toEqual([
      { provider: "google", model: "gemini", count: 2, tokens: 1200 },
    ])

    // Reordered keys ("history" first, "version": 1 last) also pass bounded preflight and restore.
    const parsed = JSON.parse(exportedPayload) as {
      version: 1
      history: HistoryRecord[]
      usage: unknown[]
    }
    const reorderedPayload = JSON.stringify(
      { history: parsed.history, usage: parsed.usage, version: parsed.version },
      null,
      2,
    )
    const reorderedFile = makeByteBackedFile(reorderedPayload)
    expect(reorderedFile.size).toBeGreaterThan(MAX_IMPORT_FILE_SIZE)

    await storage.clearHistory()
    importSpy.mockClear()
    await importHistoryFile(reorderedFile, (text) => storage.importJSON(text))
    expect(importSpy).toHaveBeenCalledWith(reorderedPayload)
    expect(await storage.listHistory()).toHaveLength(6)

    // Non-backup > 5 MiB fails preflight before reading full file.
    const externalPayload = JSON.stringify({
      external: true,
      data: "a".repeat(MAX_IMPORT_FILE_SIZE + 1024),
    })
    const externalFile = makeByteBackedFile(externalPayload)
    const importExternal = vi.fn().mockResolvedValue(undefined)
    await expect(importHistoryFile(externalFile, importExternal)).rejects.toThrow(
      "This file is too large to import.",
    )
    expect(externalFile.text).not.toHaveBeenCalled()
    expect(importExternal).not.toHaveBeenCalled()

    // Spoofed prefix > 5 MiB passes preflight only for validation, then fails without invoking importJSON.
    const spoofedPayload = JSON.stringify({
      version: 1,
      history: [{ ...baseRecord, answer: "a".repeat(MAX_IMPORT_FILE_SIZE + 1024) }],
      usage: [],
      extra_field: true,
    })
    const spoofedFile = makeByteBackedFile(spoofedPayload)
    const importSpoofed = vi.fn().mockResolvedValue(undefined)
    await expect(importHistoryFile(spoofedFile, importSpoofed)).rejects.toThrow(
      "This file is too large to import.",
    )
    expect(spoofedFile.text).toHaveBeenCalledOnce()
    expect(importSpoofed).not.toHaveBeenCalled()
  })
})