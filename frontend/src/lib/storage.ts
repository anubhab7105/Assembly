/**
 * StorageService: client-owned history, settings and daily usage.
 *
 * Web mode stores nothing server-side, so the browser owns history.
 * - BrowserStorage: IndexedDB with localStorage fallback.
 * - DesktopStorage: same browser-side store for UI settings/history; the
 *   local backend separately persists executions in SQLite and keys in the
 *   OS keyring. Do not treat SQLite as this service's source of truth.
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
  /** Distinct model families used by the completed team, when known. */
  modelFamilies?: string[]
  /** Verification summary captured by the orchestrator when the run completed. */
  verification?: {
    agents?: number
    families?: number
    rounds?: number
    disagreements_resolved?: number
    sources_verified?: number
  }
  /** Disagreements captured during the live run; omitted for legacy histories. */
  disagreements?: Array<{ id: string; agent_id: string; issue: string; resolved?: boolean }>
  /** Display-only metadata; file content is deliberately never persisted. */
  attachments?: Array<{ filename: string; media_type: string; size_bytes: number }>
}

export interface UsageRecord {
  provider: string
  model: string
  count: number
  tokens: number
}

export interface StorageService {
  listHistory(): Promise<HistoryRecord[]>
  getHistory(id: string): Promise<HistoryRecord | null>
  saveHistory(record: HistoryRecord): Promise<void>
  deleteHistory(id: string): Promise<void>
  clearHistory(): Promise<void>
  getSetting(key: string): Promise<string | null>
  setSetting(key: string, value: string): Promise<void>
  getUsage(): Promise<UsageRecord[]>
  setUsage(entries: UsageRecord[]): Promise<void>
  exportJSON(): Promise<string>
  importJSON(text: string): Promise<void>
}

const DB_NAME = "assembly"
const STORE = "kv"
const MAX_HISTORY = 200
const MAX_USAGE = 200

export class StorageError extends Error {
  constructor(operation: string) {
    super(`Couldn't ${operation} on this device: browser storage is unavailable or full. Your existing saved data was not intentionally replaced.`)
    this.name = "StorageError"
  }
}

function idb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"))
      return
    }
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE)
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error("IndexedDB open failed"))
  })
}

function storageError(operation: string, cause: unknown): StorageError {
  const error = new StorageError(operation)
  if (cause instanceof Error) error.cause = cause
  return error
}

async function idbGet<T>(key: string): Promise<T | null> {
  let idbError: unknown
  try {
    const db = await idb()
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly")
      const rq = tx.objectStore(STORE).get(key)
      rq.onsuccess = () => resolve((rq.result as T) ?? null)
      rq.onerror = () => reject(rq.error ?? new Error("IndexedDB read failed"))
      tx.onabort = () => reject(tx.error ?? new Error("IndexedDB read aborted"))
    })
  } catch (error) {
    idbError = error
  }

  try {
    if (typeof window === "undefined") return null
    const raw = window.localStorage.getItem(`assembly:${key}`)
    return raw ? (JSON.parse(raw) as T) : null
  } catch (fallbackError) {
    // Both stores failed. Don't let a later mutation overwrite data that
    // cannot be read reliably.
    const error = storageError("read saved data", fallbackError)
    error.cause = idbError
    throw error
  }
}

async function idbSet(key: string, value: unknown): Promise<void> {
  try {
    const db = await idb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite")
      tx.objectStore(STORE).put(value, key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error ?? new Error("IndexedDB write failed"))
      tx.onabort = () => reject(tx.error ?? new Error("IndexedDB write aborted"))
    })
    return
  } catch (idbError) {
    try {
      if (typeof window === "undefined") throw new Error("Browser storage is unavailable")
      window.localStorage.setItem(`assembly:${key}`, JSON.stringify(value))
      return
    } catch (fallbackError) {
      const error = storageError("save data", fallbackError)
      error.cause = idbError
      throw error
    }
  }
}

/**
 * Persist imported history and usage together. IndexedDB commits both keys
 * in one transaction; the localStorage fallback snapshots both old values
 * and rolls back if either write fails.
 */
async function idbSetImportState(history: HistoryRecord[], usage: UsageRecord[]): Promise<void> {
  let db: IDBDatabase
  try {
    db = await idb()
  } catch {
    try {
      if (typeof window === "undefined") throw new Error("Browser storage is unavailable")
      const local = window.localStorage
      const historyKey = "assembly:history"
      const usageKey = "assembly:usage"
      const previousHistory = local.getItem(historyKey)
      const previousUsage = local.getItem(usageKey)

      try {
        local.setItem(historyKey, JSON.stringify(history))
        local.setItem(usageKey, JSON.stringify(usage))
      } catch (writeError) {
        try {
          if (previousHistory === null) local.removeItem(historyKey)
          else local.setItem(historyKey, previousHistory)
          if (previousUsage === null) local.removeItem(usageKey)
          else local.setItem(usageKey, previousUsage)
        } catch {
          throw new Error("Import failed and storage rollback could not be confirmed. Do not clear site data; retry after freeing browser storage.")
        }
        throw writeError
      }
      return
    } catch (fallbackError) {
      const error = storageError("import history", fallbackError)
      if (fallbackError instanceof Error && fallbackError.message.includes("rollback could not be confirmed")) {
        error.message = fallbackError.message
      }
      throw error
    }
  }

  try {
    await new Promise<void>((resolve, reject) => {
      let tx: IDBTransaction
      try {
        tx = db.transaction(STORE, "readwrite")
        const store = tx.objectStore(STORE)
        store.put(history, "history")
        store.put(usage, "usage")
      } catch (error) {
        reject(error)
        return
      }
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error ?? new Error("Import transaction failed"))
      tx.onabort = () => reject(tx.error ?? new Error("Import transaction was aborted"))
    })
  } catch (error) {
    // A failed IndexedDB transaction aborts both puts, preserving old values.
    // Do not write a competing localStorage copy here.
    throw storageError("import history", error)
  } finally {
    db.close()
  }
}

async function idbDel(key: string): Promise<void> {
  let idbError: unknown
  try {
    const db = await idb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite")
      tx.objectStore(STORE).delete(key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error ?? new Error("IndexedDB delete failed"))
      tx.onabort = () => reject(tx.error ?? new Error("IndexedDB delete aborted"))
    })
    return
  } catch (error) {
    idbError = error
  }

  try {
    if (typeof window === "undefined") throw new Error("Browser storage is unavailable")
    window.localStorage.removeItem(`assembly:${key}`)
  } catch (fallbackError) {
    const error = storageError("delete data", fallbackError)
    error.cause = idbError
    throw error
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0
}

function normalizeHistory(value: unknown): HistoryRecord | null {
  if (!isRecord(value)) return null
  if (
    !isNonEmptyString(value.id) ||
    typeof value.question !== "string" ||
    typeof value.answer !== "string" ||
    !isNonEmptyString(value.status) ||
    !isNonEmptyString(value.created_at) ||
    typeof value.minutes !== "number" ||
    !Number.isFinite(value.minutes) ||
    ![3, 5, 10, 15].includes(value.minutes)
  ) return null

  const record: HistoryRecord = {
    id: value.id,
    question: value.question,
    answer: value.answer,
    status: value.status,
    created_at: value.created_at,
    minutes: value.minutes,
  }
  if (typeof value.consensus === "number" && Number.isFinite(value.consensus)) record.consensus = value.consensus
  else if (value.consensus === null) record.consensus = null
  if (value.confidence === "High" || value.confidence === "Moderate" || value.confidence === "Low") record.confidence = value.confidence
  else if (value.confidence === null) record.confidence = null
  if (typeof value.agentCount === "number" && Number.isFinite(value.agentCount)) record.agentCount = value.agentCount
  else if (value.agentCount === null) record.agentCount = null
  if (Array.isArray(value.providers) && value.providers.every((item) => typeof item === "string")) record.providers = value.providers
  if (typeof value.debateRounds === "number" && Number.isFinite(value.debateRounds)) record.debateRounds = value.debateRounds
  else if (value.debateRounds === null) record.debateRounds = null
  if (typeof value.tokens === "number" && Number.isFinite(value.tokens)) record.tokens = value.tokens
  else if (value.tokens === null) record.tokens = null
  if (typeof value.elapsedSeconds === "number" && Number.isFinite(value.elapsedSeconds)) record.elapsedSeconds = value.elapsedSeconds
  else if (value.elapsedSeconds === null) record.elapsedSeconds = null
  if (Array.isArray(value.modelFamilies) && value.modelFamilies.every((item) => typeof item === "string")) {
    record.modelFamilies = [...new Set(value.modelFamilies)]
  }
  if (
    isRecord(value.verification) &&
    Object.entries(value.verification).every(([key, metric]) =>
      ["agents", "families", "rounds", "disagreements_resolved", "sources_verified"].includes(key)
        ? typeof metric === "number" && Number.isFinite(metric) && metric >= 0
        : false
    )
  ) {
    record.verification = {
      ...(typeof value.verification.agents === "number" ? { agents: value.verification.agents } : {}),
      ...(typeof value.verification.families === "number" ? { families: value.verification.families } : {}),
      ...(typeof value.verification.rounds === "number" ? { rounds: value.verification.rounds } : {}),
      ...(typeof value.verification.disagreements_resolved === "number"
        ? { disagreements_resolved: value.verification.disagreements_resolved }
        : {}),
      ...(typeof value.verification.sources_verified === "number"
        ? { sources_verified: value.verification.sources_verified }
        : {}),
    }
  }
  if (
    Array.isArray(value.disagreements) &&
    value.disagreements.every((item) =>
      isRecord(item) &&
      isNonEmptyString(item.id) &&
      typeof item.agent_id === "string" &&
      typeof item.issue === "string" &&
      (item.resolved === undefined || typeof item.resolved === "boolean")
    )
  ) {
    record.disagreements = value.disagreements.map((item) => ({
      id: item.id as string,
      agent_id: item.agent_id as string,
      issue: item.issue as string,
      ...(typeof item.resolved === "boolean" ? { resolved: item.resolved } : {}),
    }))
  }
  if (
    Array.isArray(value.attachments) &&
    value.attachments.length <= 5 &&
    value.attachments.every((item) =>
      isRecord(item) &&
      typeof item.filename === "string" &&
      item.filename.length <= 120 &&
      !item.filename.includes("/") &&
      !item.filename.includes("\\") &&
      !Array.from(item.filename).some((character) => {
        const code = character.charCodeAt(0)
        return code < 32 || code === 127
      }) &&
      item.filename !== "." &&
      item.filename !== ".." &&
      item.filename.trim().length > 0 &&
      typeof item.media_type === "string" &&
      item.media_type.length <= 100 &&
      /^[a-z0-9.+-]+\/[a-z0-9.+-]+$/.test(item.media_type) &&
      typeof item.size_bytes === "number" &&
      Number.isFinite(item.size_bytes) &&
      item.size_bytes >= 0 &&
      item.size_bytes <= 256 * 1024
    )
  ) {
    record.attachments = value.attachments.map((item) => ({
      filename: item.filename as string,
      media_type: item.media_type as string,
      size_bytes: item.size_bytes as number,
    }))
  }
  return record
}

function normalizeUsage(value: unknown): UsageRecord | null {
  if (!isRecord(value)) return null
  if (!isNonEmptyString(value.provider) || typeof value.model !== "string") return null
  if (
    typeof value.count !== "number" || !Number.isFinite(value.count) || value.count < 0 ||
    typeof value.tokens !== "number" || !Number.isFinite(value.tokens) || value.tokens < 0
  ) return null
  return {
    provider: value.provider,
    model: value.model,
    count: value.count,
    tokens: value.tokens,
  }
}

function parseImport(text: string): { history: HistoryRecord[]; usage: UsageRecord[] } {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    throw new Error("Import file isn't valid JSON. No saved data was changed.")
  }
  if (!isRecord(raw) || raw.version !== 1) {
    throw new Error("Unsupported history export. Choose an Assembly JSON export (version 1). No saved data was changed.")
  }
  if (!Array.isArray(raw.history) || !Array.isArray(raw.usage)) {
    throw new Error("Import must include history and usage arrays. No saved data was changed.")
  }

  const historyById = new Map<string, HistoryRecord>()
  // Reject malformed records as a whole. Silently skipping rows makes a
  // partial import look successful and can cause users to miss lost history.
  // Valid duplicate ids remain deterministic: the first instance wins.
  raw.history.forEach((candidate, index) => {
    const record = normalizeHistory(candidate)
    if (!record) {
      throw new Error(`Import contains an invalid history record at row ${index + 1}. No saved data was changed.`)
    }
    if (!historyById.has(record.id)) historyById.set(record.id, record)
  })
  const usageByKey = new Map<string, UsageRecord>()
  raw.usage.forEach((candidate, index) => {
    const entry = normalizeUsage(candidate)
    if (!entry) {
      throw new Error(`Import contains an invalid usage record at row ${index + 1}. No saved data was changed.`)
    }
    const key = `${entry.provider}\u0000${entry.model}`
    const previous = usageByKey.get(key)
    if (!previous) usageByKey.set(key, entry)
    else usageByKey.set(key, {
      ...entry,
      count: Math.max(previous.count, entry.count),
      tokens: Math.max(previous.tokens, entry.tokens),
    })
  })
  return {
    history: [...historyById.values()].slice(0, MAX_HISTORY),
    usage: [...usageByKey.values()].slice(0, MAX_USAGE),
  }
}

class BaseStorage implements StorageService {
  async listHistory(): Promise<HistoryRecord[]> {
    const items = (await idbGet<unknown>("history")) ?? []
    if (!Array.isArray(items)) return []
    return items.map(normalizeHistory).filter((item): item is HistoryRecord => item !== null)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
  }

  async getHistory(id: string): Promise<HistoryRecord | null> {
    const items = await this.listHistory()
    return items.find((h) => h.id === id) ?? null
  }

  async saveHistory(record: HistoryRecord): Promise<void> {
    const normalized = normalizeHistory(record)
    if (!normalized) throw new Error("Invalid history record. Nothing was saved.")
    const items = (await idbGet<unknown>("history")) ?? []
    const existing = Array.isArray(items) ? items.map(normalizeHistory).filter((item): item is HistoryRecord => item !== null) : []
    const next = [normalized, ...existing.filter((h) => h.id !== normalized.id)].slice(0, MAX_HISTORY)
    await idbSet("history", next)
  }

  async deleteHistory(id: string): Promise<void> {
    const items = (await idbGet<unknown>("history")) ?? []
    const existing = Array.isArray(items) ? items.map(normalizeHistory).filter((item): item is HistoryRecord => item !== null) : []
    await idbSet("history", existing.filter((h) => h.id !== id))
  }

  async clearHistory(): Promise<void> {
    await idbDel("history")
  }

  async getSetting(key: string): Promise<string | null> {
    const value = await idbGet<unknown>(`setting:${key}`)
    return typeof value === "string" ? value : null
  }

  async setSetting(key: string, value: string): Promise<void> {
    if (typeof value !== "string") throw new Error("Setting value must be a string.")
    await idbSet(`setting:${key}`, value)
  }

  async getUsage(): Promise<UsageRecord[]> {
    const entries = (await idbGet<unknown>("usage")) ?? []
    if (!Array.isArray(entries)) return []
    return entries.map(normalizeUsage).filter((item): item is UsageRecord => item !== null)
  }

  async setUsage(entries: UsageRecord[]): Promise<void> {
    const valid = entries.map(normalizeUsage).filter((item): item is UsageRecord => item !== null)
    await idbSet("usage", valid.slice(0, MAX_USAGE))
  }

  async exportJSON(): Promise<string> {
    const history = await this.listHistory()
    const usage = await this.getUsage()
    return JSON.stringify({ version: 1, history, usage }, null, 2)
  }

  async importJSON(text: string): Promise<void> {
    // Parse and validate everything before the first write. Parse errors,
    // unsupported shapes and malformed records cannot partially update state.
    const data = parseImport(text)
    const currentHistory = (await idbGet<unknown>("history")) ?? []
    const currentUsage = (await idbGet<unknown>("usage")) ?? []
    const history = Array.isArray(currentHistory) ? currentHistory.map(normalizeHistory).filter((item): item is HistoryRecord => item !== null) : []
    const usage = Array.isArray(currentUsage) ? currentUsage.map(normalizeUsage).filter((item): item is UsageRecord => item !== null) : []

    const mergedHistory = new Map(history.map((item) => [item.id, item]))
    for (const item of data.history) mergedHistory.set(item.id, item)
    const mergedUsage = new Map(usage.map((item) => [`${item.provider}\u0000${item.model}`, item]))
    for (const item of data.usage) {
      const key = `${item.provider}\u0000${item.model}`
      const current = mergedUsage.get(key)
      mergedUsage.set(key, current ? {
        ...item,
        count: Math.max(current.count, item.count),
        tokens: Math.max(current.tokens, item.tokens),
      } : item)
    }

    // Preserve unrelated local history/settings and make repeated imports
    // idempotent. Both payloads are written as one logical transaction.
    await idbSetImportState(
      [...mergedHistory.values()].slice(0, MAX_HISTORY),
      [...mergedUsage.values()].slice(0, MAX_USAGE),
    )
  }
}

export class BrowserStorage extends BaseStorage {}
export class DesktopStorage extends BaseStorage {}

export const storage: StorageService =
  typeof window !== "undefined" && window.ASSEMBLY_APP_MODE === "desktop"
    ? new DesktopStorage()
    : new BrowserStorage();
