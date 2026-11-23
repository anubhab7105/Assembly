import { get, set, del } from "idb-keyval"

/**
 * Browser KeyVault: credentials are encrypted before persistence.
 * The passphrase-derived non-extractable CryptoKey and decrypted values live
 * only in memory. Encryption at rest does not protect against active same-
 * origin script execution while the vault is unlocked.
 */
export const KEYS_STORE_KEY = ["assembly", "keys", "encrypted", "v3"].join("_")
const LS_FALLBACK_KEY = "assembly:keys_encrypted_v3"
const LEGACY_PLAINTEXT_KEY = "assembly_keys_v1"
const LEGACY_LS_KEY = "assembly:keys_v1"
const LEGACY_ENCRYPTED_KEY = "assembly_keys_encrypted_v2"
const LEGACY_BLOBS = [LEGACY_ENCRYPTED_KEY, "assembly_keys_encrypted", "assembly_master_key"]
const KDF_ITERATIONS = 600_000
const LEGACY_KDF_ITERATIONS = 210_000
const FORMAT_VERSION = 3
const MIN_NEW_PASSPHRASE_LENGTH = 12
const MIN_LEGACY_PASSPHRASE_LENGTH = 8

type EncryptedRecord = {
  v: number
  kdf: "PBKDF2-SHA-256"
  iterations: number
  salt: string
  iv: string
  ciphertext: string
}

export class KeyStorageError extends Error {
  constructor(message = "Couldn't update saved keys on this device. Secure storage is unavailable or the change could not be verified.") {
    super(message)
    this.name = "KeyStorageError"
  }
}
export class VaultLockedError extends Error {
  constructor(message = "Unlock your saved keys with your vault passphrase before continuing.") {
    super(message)
    this.name = "VaultLockedError"
  }
}

function isKeysRecord(value: unknown): value is Record<string, string> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false
  return Object.entries(value as Record<string, unknown>).every(
    ([key, item]) => typeof key === "string" && typeof item === "string",
  )
}
function isEncryptedRecord(value: unknown): value is EncryptedRecord {
  if (typeof value !== "object" || value === null) return false
  const record = value as Partial<EncryptedRecord>
  return record.v === FORMAT_VERSION
    && record.kdf === "PBKDF2-SHA-256"
    && typeof record.iterations === "number"
    && record.iterations >= KDF_ITERATIONS
    && typeof record.salt === "string"
    && typeof record.iv === "string"
    && typeof record.ciphertext === "string"
}
function toBase64(bytes: Uint8Array): string {
  let binary = ""
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000))
  }
  return btoa(binary)
}
function fromBase64(value: string): Uint8Array {
  const binary = atob(value)
  return Uint8Array.from(binary, char => char.charCodeAt(0))
}
async function deriveKey(
  passphrase: string,
  salt: Uint8Array,
  iterations = KDF_ITERATIONS,
): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"],
  )
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: salt as BufferSource, iterations, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  )
}
function makeSalt(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(16))
}
async function encryptRecord(
  keys: Record<string, string>,
  key: CryptoKey,
  salt: Uint8Array,
): Promise<EncryptedRecord> {
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv as BufferSource },
    key,
    new TextEncoder().encode(JSON.stringify(keys)),
  )
  return {
    v: FORMAT_VERSION,
    kdf: "PBKDF2-SHA-256",
    iterations: KDF_ITERATIONS,
    salt: toBase64(salt),
    iv: toBase64(iv),
    ciphertext: toBase64(new Uint8Array(ciphertext)),
  }
}
async function decryptRecord(record: EncryptedRecord, key: CryptoKey): Promise<Record<string, string>> {
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: fromBase64(record.iv) as BufferSource },
    key,
    fromBase64(record.ciphertext) as BufferSource,
  )
  const parsed: unknown = JSON.parse(new TextDecoder().decode(plaintext))
  if (!isKeysRecord(parsed)) throw new Error("Invalid vault payload")
  return { ...parsed }
}

export class KeyVault {
  private cache: Record<string, string> = {}
  private cryptoKey: CryptoKey | null = null
  private salt: Uint8Array | null = null
  private loaded = false
  private writeChain: Promise<void> = Promise.resolve()
  private primaryStoreAvailable = typeof indexedDB !== "undefined"

  private async readCurrentEncrypted(): Promise<unknown> {
    try {
      if (this.primaryStoreAvailable) return await get<unknown>(KEYS_STORE_KEY)
      if (typeof window === "undefined") return undefined
      const raw = window.localStorage.getItem(LS_FALLBACK_KEY)
      return raw ? JSON.parse(raw) as unknown : undefined
    } catch {
      throw new KeyStorageError()
    }
  }

  private async writeStored(value: EncryptedRecord): Promise<void> {
    if (this.primaryStoreAvailable) {
      try {
        await set(KEYS_STORE_KEY, value)
      } catch {
        throw new KeyStorageError()
      }
    } else {
      try {
        if (typeof window === "undefined") throw new Error("No browser storage")
        window.localStorage.setItem(LS_FALLBACK_KEY, JSON.stringify(value))
      } catch {
        throw new KeyStorageError()
      }
    }

    const verified = await this.readCurrentEncrypted()
    if (
      !isEncryptedRecord(verified)
      || verified.ciphertext !== value.ciphertext
      || verified.salt !== value.salt
      || verified.iv !== value.iv
    ) {
      throw new KeyStorageError(
        "Secure storage did not retain the encrypted vault. The original data was left untouched.",
      )
    }
  }

  private enqueue<T>(work: () => Promise<T>): Promise<T> {
    const run = this.writeChain.then(work, work)
    this.writeChain = run.then(() => undefined, () => undefined)
    return run
  }

  async hasPersisted(): Promise<boolean> {
    if ((await this.readCurrentEncrypted()) !== undefined) return true
    return (await this.readLegacyPlaintext()) !== undefined
  }

  isUnlocked(): boolean {
    return this.cryptoKey !== null && this.loaded
  }

  async unlock(passphrase: string): Promise<Record<string, string>> {
    if (!passphrase || passphrase.length < MIN_LEGACY_PASSPHRASE_LENGTH) {
      throw new Error("Vault passphrase must contain at least 8 characters.")
    }

    const stored = await this.readCurrentEncrypted()
    let keys: Record<string, string> = {}
    let nextKey: CryptoKey
    let nextSalt: Uint8Array

    if (isEncryptedRecord(stored)) {
      try {
        nextSalt = fromBase64(stored.salt)
        nextKey = await deriveKey(passphrase, nextSalt, stored.iterations)
        keys = await decryptRecord(stored, nextKey)
      } catch {
        throw new Error("Incorrect passphrase or damaged vault. No saved data was changed.")
      }
      await this.removeLegacyPlaintext()
    } else {
      const legacyPlaintext = stored === undefined ? await this.readLegacyPlaintext() : stored
      if (legacyPlaintext !== undefined && !isKeysRecord(legacyPlaintext)) {
        throw new Error("Saved vault format is invalid. The existing record was left untouched.")
      }

      if (legacyPlaintext !== undefined) {
        if (passphrase.length < MIN_NEW_PASSPHRASE_LENGTH) {
          throw new Error("Create a new vault passphrase with at least 12 characters to protect migrated keys.")
        }
        keys = { ...legacyPlaintext }
        nextSalt = makeSalt()
        nextKey = await deriveKey(passphrase, nextSalt)
        await this.writeStored(await encryptRecord(keys, nextKey, nextSalt))
        await this.removeLegacyPlaintext()
      } else {
        const legacy = await get<{
          v: number
          salt: string
          iv: string
          ciphertext: string
        } | undefined>(LEGACY_ENCRYPTED_KEY).catch(() => undefined)

        if (legacy) {
          try {
            const legacySalt = fromBase64(legacy.salt)
            const legacyKey = await deriveKey(passphrase, legacySalt, LEGACY_KDF_ITERATIONS)
            const bytes = await crypto.subtle.decrypt(
              { name: "AES-GCM", iv: fromBase64(legacy.iv) as BufferSource },
              legacyKey,
              fromBase64(legacy.ciphertext) as BufferSource,
            )
            const parsed: unknown = JSON.parse(new TextDecoder().decode(bytes))
            if (!isKeysRecord(parsed)) throw new Error("Invalid legacy payload")
            keys = { ...parsed }
          } catch {
            throw new Error("Incorrect legacy passphrase or damaged vault. Nothing was deleted.")
          }
          nextSalt = makeSalt()
          nextKey = await deriveKey(passphrase, nextSalt)
          await this.writeStored(await encryptRecord(keys, nextKey, nextSalt))
          await this.clearLegacyEncryptedBlobs()
        } else {
          if (passphrase.length < MIN_NEW_PASSPHRASE_LENGTH) {
            throw new Error("Create a vault passphrase with at least 12 characters.")
          }
          nextSalt = makeSalt()
          nextKey = await deriveKey(passphrase, nextSalt)
          await this.writeStored(await encryptRecord({}, nextKey, nextSalt))
        }
      }
    }

    this.cryptoKey = nextKey
    this.salt = nextSalt
    this.cache = keys
    this.loaded = true
    return { ...keys }
  }

  private async readLegacyPlaintext(): Promise<unknown> {
    if (this.primaryStoreAvailable) {
      try { return await get<unknown>(LEGACY_PLAINTEXT_KEY) } catch { throw new KeyStorageError() }
    }
    try {
      if (typeof window === "undefined") return undefined
      const raw = window.localStorage.getItem(LEGACY_LS_KEY)
      return raw ? JSON.parse(raw) as unknown : undefined
    } catch {
      throw new KeyStorageError()
    }
  }

  private async removeLegacyPlaintext(): Promise<void> {
    if (this.primaryStoreAvailable) {
      try { await del(LEGACY_PLAINTEXT_KEY) } catch {
        throw new KeyStorageError("The encrypted vault is saved, but an old plaintext copy could not be removed. Try unlocking again after browser storage is available.")
      }
      try {
        if (typeof window !== "undefined") window.localStorage.removeItem(LEGACY_LS_KEY)
      } catch {
        throw new KeyStorageError("The encrypted vault is saved, but an old localStorage copy could not be removed.")
      }
    } else {
      try {
        if (typeof window !== "undefined") window.localStorage.removeItem(LEGACY_LS_KEY)
      } catch {
        throw new KeyStorageError("The encrypted vault is saved, but an old localStorage copy could not be removed.")
      }
    }
  }

  private async ensureUnlocked(): Promise<void> {
    if (!this.cryptoKey || !this.salt || !this.loaded) throw new VaultLockedError()
  }

  async setKey(provider: string, key: string): Promise<void> {
    const id = (provider || "").trim()
    const secret = (key || "").trim()
    if (!id) throw new Error("Unknown provider. Nothing was saved.")
    if (!secret) throw new Error("Empty key. Nothing was saved.")
    await this.ensureUnlocked()
    await this.enqueue(async () => {
      const next = { ...this.cache, [id]: secret }
      const encrypted = await encryptRecord(next, this.cryptoKey!, this.salt!)
      await this.writeStored(encrypted)
      this.cache = next
    })
  }

  async removeKey(provider: string): Promise<void> {
    const id = (provider || "").trim()
    if (!id) return
    await this.ensureUnlocked()
    await this.enqueue(async () => {
      if (!(id in this.cache)) return
      const next = { ...this.cache }
      delete next[id]
      await this.writeStored(await encryptRecord(next, this.cryptoKey!, this.salt!))
      this.cache = next
    })
  }

  async getKey(provider: string): Promise<string | null> {
    await this.ensureUnlocked()
    return this.cache[provider] ?? null
  }

  async allKeys(): Promise<Record<string, string>> {
    await this.ensureUnlocked()
    return { ...this.cache }
  }

  async lock(): Promise<void> {
    this.cache = {}
    this.cryptoKey = null
    this.salt = null
    this.loaded = false
  }

  async clearAll(): Promise<void> {
    await this.enqueue(async () => {
      if (this.primaryStoreAvailable) {
        try {
          await del(KEYS_STORE_KEY)
          await del(LEGACY_PLAINTEXT_KEY)
        } catch {
          throw new KeyStorageError()
        }
      }
      try {
        if (typeof window !== "undefined") {
          window.localStorage.removeItem(LS_FALLBACK_KEY)
          window.localStorage.removeItem(LEGACY_LS_KEY)
        }
      } catch {
        throw new KeyStorageError()
      }
      await this.clearLegacyEncryptedBlobs()
      this.cache = {}
      this.cryptoKey = null
      this.salt = null
      this.loaded = false
    })
  }

  async hasLegacyEncrypted(): Promise<boolean> {
    try {
      return (await get<unknown>(LEGACY_ENCRYPTED_KEY)) !== undefined
    } catch {
      return false
    }
  }

  private async clearLegacyEncryptedBlobs(): Promise<void> {
    if (this.primaryStoreAvailable) {
      for (const key of LEGACY_BLOBS) {
        try { await del(key) } catch { /* the replacement ciphertext is verified */ }
      }
    }
    try {
      if (typeof window !== "undefined") window.localStorage.removeItem("assembly_remember_keys")
    } catch { /* best-effort cleanup */ }
  }
}

export const globalVault = new KeyVault()
