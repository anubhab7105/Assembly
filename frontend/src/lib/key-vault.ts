import { get, set, del } from "idb-keyval"

/**
 * KeyVault: one canonical browser-side store for provider credentials.
 *
 * Every `setKey` writes through to persistent storage (IndexedDB via
 * idb-keyval, with a localStorage mirror used only when IndexedDB throws),
 * so a plain Save survives a normal page refresh with no extra step.
 * Reads load from the same store before serving, so initialization can
 * never overwrite saved values with empty defaults.
 *
 * Keys travel to the backend only transiently inside `/api/run` and
 * `/api/keys/test` HTTPS bodies; they are never written to the server,
 * URLs, or logs from here.
 */

export const KEYS_STORE_KEY = "assembly_keys_v1"
const LS_FALLBACK_KEY = "assembly:keys_v1"

const LEGACY_ENCRYPTED_KEY = "assembly_keys_encrypted_v2"
const LEGACY_BLOBS = [LEGACY_ENCRYPTED_KEY, "assembly_keys_encrypted", "assembly_master_key"]

export class KeyStorageError extends Error {
  constructor(message = "Couldn't save keys on this device (storage unavailable or full). Nothing was saved.") {
    super(message)
    this.name = "KeyStorageError"
  }
}

function isKeysRecord(v: unknown): v is Record<string, string> {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return false
  return Object.entries(v as Record<string, unknown>).every(
    ([k, val]) => typeof k === "string" && typeof val === "string",
  )
}

function b64ToBuf(b64: string): Uint8Array {
  const s = atob(b64)
  const out = new Uint8Array(s.length)
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i)
  return out
}

async function deriveKek(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"],
  )
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: salt as BufferSource, iterations: 210_000, hash: "SHA-256" },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  )
}

function lsGet(): Record<string, string> | null {
  try {
    if (typeof window === "undefined") return null
    const raw = window.localStorage.getItem(LS_FALLBACK_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    return isKeysRecord(parsed) ? { ...parsed } : null
  } catch {
    return null
  }
}

export class KeyVault {
  private cache: Record<string, string> = {}
  private loadOnce: Promise<void> | null = null
  private writeChain: Promise<void> = Promise.resolve()

  private ensureLoaded(): Promise<void> {
    if (!this.loadOnce) this.loadOnce = this.loadFromStores()
    return this.loadOnce
  }

  private async loadFromStores(): Promise<void> {
    // Primary first; the localStorage mirror is consulted only when the
    // primary is absent (never written while the primary is healthy, so a
    // deliberate clear cannot resurrect stale fallback copies).
    try {
      const v = await get<unknown>(KEYS_STORE_KEY)
      if (v !== undefined) {
        if (isKeysRecord(v)) this.cache = { ...v }
        return
      }
    } catch {
      // IndexedDB unavailable: fall through to the mirror.
    }
    const fb = lsGet()
    if (fb) this.cache = fb
  }

  private async readCanonical(): Promise<Record<string, string>> {
    try {
      const v = await get<unknown>(KEYS_STORE_KEY)
      if (v !== undefined) return isKeysRecord(v) ? { ...v } : { ...this.cache }
    } catch {
      // Fall through to the mirror.
    }
    return lsGet() ?? { ...this.cache }
  }

  private async writeCanonical(next: Record<string, string>): Promise<void> {
    const snapshot = { ...next }
    try {
      await set(KEYS_STORE_KEY, snapshot)
      // Primary healthy: drop any stale fallback copy (best effort).
      try {
        if (typeof window !== "undefined") window.localStorage.removeItem(LS_FALLBACK_KEY)
      } catch {
        // Mirror cleanup failure is harmless while the primary holds truth.
      }
      return
    } catch {
      // IndexedDB failed: mirror to localStorage so the save still survives.
    }
    try {
      if (typeof window === "undefined") throw new Error("no window")
      window.localStorage.setItem(LS_FALLBACK_KEY, JSON.stringify(snapshot))
      return
    } catch {
      throw new KeyStorageError()
    }
  }

  private enqueue<T>(work: () => Promise<T>): Promise<T> {
    const run = this.writeChain.then(work, work)
    // Keep the chain alive for later writes even if this one rejects.
    this.writeChain = run.then(
      () => undefined,
      () => undefined,
    )
    return run
  }

  async setKey(provider: string, key: string): Promise<void> {
    const p = (provider || "").trim()
    const k = (key || "").trim()
    if (!p) throw new Error("Unknown provider. Nothing was saved.")
    if (!k) throw new Error("Empty key. Nothing was saved.")
    await this.ensureLoaded()
    const merged = await this.enqueue(async () => {
      const cur = await this.readCanonical()
      const next = { ...cur, [p]: k }
      await this.writeCanonical(next)
      return next
    })
    this.cache = merged
  }

  async removeKey(provider: string): Promise<void> {
    const p = (provider || "").trim()
    if (!p) return
    await this.ensureLoaded()
    const merged = await this.enqueue(async () => {
      const cur = await this.readCanonical()
      if (!(p in cur)) return cur
      const next = { ...cur }
      delete next[p]
      await this.writeCanonical(next)
      return next
    })
    this.cache = merged
  }

  async getKey(provider: string): Promise<string | null> {
    await this.ensureLoaded()
    const cur = await this.readCanonical().catch(() => ({ ...this.cache }))
    this.cache = cur
    return cur[provider] ?? null
  }

  async allKeys(): Promise<Record<string, string>> {
    await this.ensureLoaded()
    const cur = await this.readCanonical().catch(() => ({ ...this.cache }))
    this.cache = cur
    return { ...cur }
  }

  /** Whether the canonical store holds any keys (no decryption involved). */
  async hasPersisted(): Promise<boolean> {
    const keys = await this.allKeys().catch(() => ({} as Record<string, string>))
    return Object.keys(keys).length > 0
  }

  async clearAll(): Promise<void> {
    await this.ensureLoaded()
    const merged = await this.enqueue(async () => {
      const next: Record<string, string> = {}
      await this.writeCanonical(next)
      await this.clearLegacyBlobs()
      return next
    })
    this.cache = merged
  }

  /** A pre-fix encrypted blob exists but the canonical store is empty. */
  async hasLegacyEncrypted(): Promise<boolean> {
    try {
      const stored = await get<unknown>(LEGACY_ENCRYPTED_KEY)
      return stored !== undefined
    } catch {
      return false
    }
  }

  /**
   * One-time migration for pre-fix users: decrypt the legacy passphrase
   * blob into the canonical store, then delete the legacy blobs.
   * Wrong passphrase (or corruption) throws and deletes nothing.
   */
  async migrateLegacy(passphrase: string): Promise<Record<string, string>> {
    if (!passphrase || passphrase.length < 8) throw new Error("Passphrase must be at least 8 characters.")
    const stored = await get<{ v: number; salt: string; iv: string; ciphertext: string } | undefined>(
      LEGACY_ENCRYPTED_KEY,
    ).catch(() => undefined)
    if (!stored) throw new Error("No saved vault found on this device.")
    let decrypted: Record<string, string>
    try {
      const kek = await deriveKek(passphrase, b64ToBuf(stored.salt))
      const bytes = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: b64ToBuf(stored.iv) as BufferSource },
        kek,
        b64ToBuf(stored.ciphertext) as BufferSource,
      )
      const parsed: unknown = JSON.parse(new TextDecoder().decode(bytes))
      if (!isKeysRecord(parsed)) throw new Error("bad shape")
      decrypted = { ...parsed }
    } catch {
      throw new Error("Wrong passphrase. Nothing was deleted. Try again or use Clear all keys.")
    }
    await this.ensureLoaded()
    const merged = await this.enqueue(async () => {
      const cur = await this.readCanonical()
      const next = { ...cur, ...decrypted }
      await this.writeCanonical(next)
      await this.clearLegacyBlobs()
      return next
    })
    this.cache = merged
    return { ...merged }
  }

  private async clearLegacyBlobs(): Promise<void> {
    for (const k of LEGACY_BLOBS) {
      try {
        await del(k)
      } catch {
        // Best effort: one stuck legacy key must not fail an explicit clear.
      }
    }
    try {
      if (typeof window !== "undefined") window.localStorage.removeItem("assembly_remember_keys")
    } catch {
      // ignore
    }
  }
}

export const globalVault = new KeyVault()
