/** KeyVault encryption and migration regression tests. */
import { describe, it, expect, vi, beforeEach } from "vitest"

const store = new Map<string, unknown>()
vi.mock("idb-keyval", () => ({
  get: vi.fn((key: string) => Promise.resolve(store.get(key))),
  set: vi.fn((key: string, value: unknown) => { store.set(key, value); return Promise.resolve() }),
  del: vi.fn((key: string) => { store.delete(key); return Promise.resolve() }),
}))

import { get, set } from "idb-keyval"
import { KeyVault, KeyStorageError, VaultLockedError, KEYS_STORE_KEY } from "./key-vault"

const CANARY_A = "gsk-CANARY-VAULT-A1"
const CANARY_B = "tvly-CANARY-VAULT-B2"
const PASS = "correct horse battery staple"

function mockLocalStorage() {
  const bag = new Map<string, string>()
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => bag.get(key) ?? null,
    setItem: (key: string, value: string) => { bag.set(key, value) },
    removeItem: (key: string) => { bag.delete(key) },
  } as Storage)
  return bag
}

async function makeLegacyBlob(passphrase: string, keys: Record<string, string>) {
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(passphrase), "PBKDF2", false, ["deriveKey"])
  const legacyKey = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: 210_000, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  )
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv as BufferSource },
    legacyKey,
    new TextEncoder().encode(JSON.stringify(keys)),
  )
  const b64 = (value: Uint8Array | ArrayBuffer) => btoa(String.fromCharCode(...(value instanceof Uint8Array ? value : new Uint8Array(value))))
  await set("assembly_keys_encrypted_v2", { v: 2, salt: b64(salt), iv: b64(iv), ciphertext: b64(ciphertext) })
}

describe("KeyVault encrypted persistence", () => {
  beforeEach(() => {
    store.clear()
    mockLocalStorage()
    vi.stubGlobal("indexedDB", {})
    vi.mocked(get).mockImplementation((key) => Promise.resolve(store.get(String(key))))
    vi.mocked(set).mockImplementation((key, value) => { store.set(String(key), value); return Promise.resolve() })
  })

  it("stores ciphertext only and survives a lock/reload/unlock cycle", async () => {
    const vault = new KeyVault()
    await vault.unlock(PASS)
    await vault.setKey("groq", CANARY_A)
    await vault.setKey("tavily", CANARY_B)
    const raw = JSON.stringify(store.get(KEYS_STORE_KEY))
    expect(raw).not.toContain(CANARY_A)
    expect(raw).not.toContain(CANARY_B)
    expect(raw).toContain("PBKDF2-SHA-256")
    await vault.lock()
    await expect(vault.allKeys()).rejects.toBeInstanceOf(VaultLockedError)
    const reloaded = new KeyVault()
    await expect(reloaded.unlock("incorrect passphrase")).rejects.toThrow(/Incorrect passphrase/)
    expect(await reloaded.unlock(PASS)).toEqual({ groq: CANARY_A, tavily: CANARY_B })
  })

  it("encrypts localStorage fallback values when IndexedDB is unavailable", async () => {
    const fallback = mockLocalStorage()
    vi.stubGlobal("indexedDB", undefined)
    vi.mocked(get).mockRejectedValue(new Error("IndexedDB unavailable"))
    const vault = new KeyVault()
    await vault.unlock(PASS)
    await vault.setKey("groq", CANARY_A)
    const raw = fallback.get("assembly:keys_encrypted_v3") ?? ""
    expect(raw).not.toContain(CANARY_A)
    expect(JSON.parse(raw).kdf).toBe("PBKDF2-SHA-256")
    await vault.lock()
    expect(await new KeyVault().unlock(PASS)).toEqual({ groq: CANARY_A })
  })

  it("migrates legacy plaintext only after ciphertext has been verified", async () => {
    await set("assembly_keys_v1", { groq: CANARY_A })
    const vault = new KeyVault()
    expect(await vault.hasPersisted()).toBe(true)
    await vault.unlock(PASS)
    const raw = JSON.stringify(store.get(KEYS_STORE_KEY))
    expect(raw).not.toContain(CANARY_A)
    expect(store.has("assembly_keys_v1")).toBe(false)
    expect(await vault.getKey("groq")).toBe(CANARY_A)
  })

  it("preserves legacy plaintext when encrypted persistence fails", async () => {
    await set("assembly_keys_v1", { groq: CANARY_A })
    vi.mocked(set).mockRejectedValue(new Error("IndexedDB write failed"))
    const vault = new KeyVault()
    await expect(vault.unlock(PASS)).rejects.toBeInstanceOf(KeyStorageError)
    expect(store.get("assembly_keys_v1")).toEqual({ groq: CANARY_A })
  })

  it("migrates the previous encrypted v2 blob without losing credentials", async () => {
    await makeLegacyBlob("old vault passphrase", { groq: CANARY_A })
    const vault = new KeyVault()
    await expect(vault.unlock("not the old phrase")).rejects.toThrow(/Incorrect legacy passphrase/)
    expect(await vault.hasLegacyEncrypted()).toBe(true)
    expect(await vault.unlock("old vault passphrase")).toEqual({ groq: CANARY_A })
    expect(await vault.hasLegacyEncrypted()).toBe(false)
    expect(JSON.stringify(store.get(KEYS_STORE_KEY))).not.toContain(CANARY_A)
  })

  it("rejects weak initial passphrases and empty keys", async () => {
    const vault = new KeyVault()
    await expect(vault.unlock("short")).rejects.toThrow(/at least 8/)
    await expect(vault.unlock("short pass")).rejects.toThrow(/at least 12/)
    await vault.unlock(PASS)
    await expect(vault.setKey("groq", " ")).rejects.toThrow(/Empty key/)
  })

  it("detects tampered ciphertext and fails closed", async () => {
    const vault = new KeyVault()
    await vault.unlock(PASS)
    await vault.setKey("groq", CANARY_A)
    await vault.lock()
    const record = store.get(KEYS_STORE_KEY) as { ciphertext: string }
    store.set(KEYS_STORE_KEY, { ...record, ciphertext: record.ciphertext.slice(0, -4) + "AAAA" })
    await expect(new KeyVault().unlock(PASS)).rejects.toThrow(/Incorrect passphrase/)
  })
})
