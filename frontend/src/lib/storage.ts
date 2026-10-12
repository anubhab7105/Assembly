/**
 * StorageService: client-owned history, settings and daily usage.
 *
 * Web mode stores nothing server-side, so the browser owns history.
 * Two implementations share one interface:
 * - BrowserStorage: IndexedDB (history, settings, daily usage).
 * - DesktopStorage: same IndexedDB store (desktop shell serves the same
 *   build; the backend SQLite is only a local run cache, not the source
 *   of truth for the UI).
 */

export interface HistoryRecord {
  id: string
  question: string
  answer: string
  status: string
  created_at: string
  minutes: number
  consensus?: number | null
  confidence?: "High" | "Moderate" | "Low" | null
  agentCount?: number | null
  providers?: string[]
  debateRounds?: number | null
  tokens?: number | null
  elapsedSeconds?: number | null
}

export interface StorageService {
  listHistory(): Promise<HistoryRecord[]>
  getHistory(id: string): Promise<HistoryRecord | null>
  saveHistory(record: HistoryRecord): Promise<void>
  deleteHistory(id: string): Promise<void>
  clearHistory(): Promise<void>
  getSetting(key: string): Promise<string | null>
  setSetting(key: string, value: string): Promise<void>
  getUsage(): Promise<{ provider: string; model: string; count: number; tokens: number }[]>
  setUsage(entries: { provider: string; model: string; count: number; tokens: number }[]): Promise<void>
  exportJSON(): Promise<string>
  importJSON(text: string): Promise<void>
}

const DB_NAME = "assembly"
const STORE = "kv"

function idb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"))
      return
    }
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE)
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function idbGet<T>(key: string): Promise<T | null> {
  try {
    const db = await idb()
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly")
      const rq = tx.objectStore(STORE).get(key)
      rq.onsuccess = () => resolve((rq.result as T) ?? null)
      rq.onerror = () => reject(rq.error)
    })
  } catch {
    try {
      const raw = window.localStorage.getItem(`assembly:${key}`)
      return raw ? (JSON.parse(raw) as T) : null
    } catch {
      return null
    }
  }
}

async function idbSet(key: string, value: unknown): Promise<void> {
  try {
    const db = await idb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite")
      tx.objectStore(STORE).put(value, key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    try {
      window.localStorage.setItem(`assembly:${key}`, JSON.stringify(value))
    } catch {
      // Storage full/blocked: history degrades to memory-only.
    }
  }
}

async function idbDel(key: string): Promise<void> {
  try {
    const db = await idb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite")
      tx.objectStore(STORE).delete(key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    try {
      window.localStorage.removeItem(`assembly:${key}`)
    } catch {
      // ignore
    }
  }
}

class BaseStorage implements StorageService {
  async listHistory(): Promise<HistoryRecord[]> {
    const items = (await idbGet<HistoryRecord[]>("history")) ?? []
    return [...items].sort((a, b) => b.created_at.localeCompare(a.created_at))
  }
  async getHistory(id: string): Promise<HistoryRecord | null> {
    const items = await this.listHistory()
    return items.find((h) => h.id === id) ?? null
  }
  async saveHistory(record: HistoryRecord): Promise<void> {
    const items = (await idbGet<HistoryRecord[]>("history")) ?? []
    const next = [record, ...items.filter((h) => h.id !== record.id)].slice(0, 200)
    await idbSet("history", next)
  }
  async deleteHistory(id: string): Promise<void> {
    const items = (await idbGet<HistoryRecord[]>("history")) ?? []
    await idbSet(
      "history",
      items.filter((h) => h.id !== id),
    )
  }
  async clearHistory(): Promise<void> {
    await idbDel("history")
  }
  async getSetting(key: string): Promise<string | null> {
    return idbGet<string>(`setting:${key}`)
  }
  async setSetting(key: string, value: string): Promise<void> {
    await idbSet(`setting:${key}`, value)
  }
  async getUsage() {
    return (await idbGet<{ provider: string; model: string; count: number; tokens: number }[]>("usage")) ?? []
  }
  async setUsage(entries: { provider: string; model: string; count: number; tokens: number }[]) {
    await idbSet("usage", entries)
  }
  async exportJSON(): Promise<string> {
    const history = (await idbGet("history")) ?? []
    const usage = (await idbGet("usage")) ?? []
    return JSON.stringify({ version: 1, history, usage }, null, 2)
  }
  async importJSON(text: string): Promise<void> {
    const data = JSON.parse(text)
    if (Array.isArray(data.history)) await idbSet("history", data.history.slice(0, 200))
    if (Array.isArray(data.usage)) await idbSet("usage", data.usage.slice(0, 200))
  }
}

export class BrowserStorage extends BaseStorage {}
export class DesktopStorage extends BaseStorage {}

export const storage: StorageService =
  typeof window !== "undefined" && (window as any).ASSEMBLY_APP_MODE === "desktop"
    ? new DesktopStorage()
    : new BrowserStorage();
