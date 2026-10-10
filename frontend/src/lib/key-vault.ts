import { get, set, del } from "idb-keyval"

/**
 * KeyVault: API keys live in memory by default (lost on reload).
 *
 * "Remember on this device" encrypts keys with WebCrypto AES-GCM, the
 * data key wrapped by a key derived from a USER PASSPHRASE via PBKDF2.
 * No passphrase = no persistence. The passphrase itself is never stored.
 */

const DB_KEY = "assembly_keys_encrypted_v2"

function bufToB64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  let s = ""
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i])
  return btoa(s)
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

export class KeyVault {
  private inMemoryKeys: Record<string, string> = {}
  public remember: boolean = false
  private passphrase: string | null = null

  constructor() {
    if (typeof window !== "undefined") {
      this.remember = window.localStorage.getItem("assembly_remember_keys") === "true"
    }
  }

  /** Unlock persistence with the user's passphrase (kept in memory only). */
  unlock(passphrase: string) {
    this.passphrase = passphrase
  }

  lock() {
    this.passphrase = null
  }

  get unlocked(): boolean {
    return this.passphrase !== null && this.passphrase.length >= 8
  }

  setRemember(remember: boolean) {
    this.remember = remember
    if (typeof window !== "undefined") {
      window.localStorage.setItem("assembly_remember_keys", String(remember))
    }
    if (!remember) {
      this.lock()
      void this.clearPersisted()
    }
  }

  async setKey(provider: string, key: string) {
    this.inMemoryKeys[provider] = key
    if (this.remember && this.unlocked) {
      await this.persist()
    }
  }

  async getKey(provider: string): Promise<string | null> {
    if (this.inMemoryKeys[provider]) return this.inMemoryKeys[provider]
    if (this.remember && this.unlocked) {
      await this.loadPersisted()
      return this.inMemoryKeys[provider] || null
    }
    return null
  }

  async allKeys(): Promise<Record<string, string>> {
    if (this.remember && this.unlocked && Object.keys(this.inMemoryKeys).length === 0) {
      await this.loadPersisted()
    }
    return { ...this.inMemoryKeys }
  }

  /** Whether an encrypted blob exists (no decryption, never exposes keys). */
  async hasPersisted(): Promise<boolean> {
    try {
      const stored = await get(DB_KEY)
      return stored !== undefined
    } catch {
      return false
    }
  }

  async clearAll() {
    this.inMemoryKeys = {}
    this.lock()
    this.setRemember(false)
    await this.clearPersisted()
  }

  private async persist() {
    if (!this.passphrase) return
    const salt = crypto.getRandomValues(new Uint8Array(16))
    const iv = crypto.getRandomValues(new Uint8Array(12))
    const kek = await deriveKek(this.passphrase, salt)
    const encoded = new TextEncoder().encode(JSON.stringify(this.inMemoryKeys))
    const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv: iv as BufferSource }, kek, encoded)
    await set(DB_KEY, {
      v: 2,
      salt: bufToB64(salt),
      iv: bufToB64(iv),
      ciphertext: bufToB64(ciphertext),
    })
    // Drop legacy v1 blob if present.
    await del("assembly_keys_encrypted")
    await del("assembly_master_key")
  }

  private async loadPersisted() {
    const stored = await get<{ v: number; salt: string; iv: string; ciphertext: string } | undefined>(DB_KEY)
    if (!stored || !this.passphrase) return
    try {
      const kek = await deriveKek(this.passphrase, b64ToBuf(stored.salt))
      const decrypted = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: b64ToBuf(stored.iv) as BufferSource },
        kek,
        b64ToBuf(stored.ciphertext) as BufferSource,
      )
      this.inMemoryKeys = JSON.parse(new TextDecoder().decode(decrypted))
    } catch {
      this.inMemoryKeys = {}
      throw new Error("Wrong passphrase or corrupted vault.")
    }
  }

  private async clearPersisted() {
    await del(DB_KEY)
    await del("assembly_keys_encrypted")
    await del("assembly_master_key")
  }
}

export const globalVault = new KeyVault()
