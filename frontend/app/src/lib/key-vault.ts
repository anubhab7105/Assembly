import { get, set, del } from "idb-keyval"

/**
 * KeyVault manages API keys securely on the client.
 * 
 * Tradeoffs:
 * - "In-memory" (default): Keys are lost on reload. Highly secure as they never touch disk.
 * - "Remember on device": Uses IndexedDB via WebCrypto. The keys are encrypted at rest 
 *   using a generated master key, but since the master key must also be stored locally 
 *   (or derived from a local secret) to allow auto-unlocking, this primarily protects 
 *   against casual snooping of the raw IDB files on disk, not against targeted local malware 
 *   or XSS (as XSS can just call decrypt()).
 */

const DB_KEY = "assembly_keys_encrypted"

export class KeyVault {
  private inMemoryKeys: Record<string, string> = {}
  private masterKey: CryptoKey | null = null
  public remember: boolean = false

  constructor() {
    if (typeof window !== "undefined") {
      this.remember = window.localStorage.getItem("assembly_remember_keys") === "true"
    }
  }

  setRemember(remember: boolean) {
    this.remember = remember
    if (typeof window !== "undefined") {
      window.localStorage.setItem("assembly_remember_keys", String(remember))
    }
    if (!remember) {
      this.clearPersisted()
    }
  }

  async setKey(provider: string, key: string) {
    this.inMemoryKeys[provider] = key
    if (this.remember) {
      await this.persist()
    }
  }

  async getKey(provider: string): Promise<string | null> {
    if (this.inMemoryKeys[provider]) return this.inMemoryKeys[provider]
    
    if (this.remember) {
      await this.loadPersisted()
      return this.inMemoryKeys[provider] || null
    }
    
    return null
  }

  private async getMasterKey(): Promise<CryptoKey> {
    if (this.masterKey) return this.masterKey

    // In a real implementation, you might derive this from a user password or a locally
    // stored high-entropy secret. For this demo, we generate and store an exportable key.
    const storedKey = await get("assembly_master_key")
    if (storedKey) {
      this.masterKey = await crypto.subtle.importKey(
        "jwk",
        storedKey,
        { name: "AES-GCM" },
        true,
        ["encrypt", "decrypt"]
      )
    } else {
      this.masterKey = await crypto.subtle.generateKey(
        { name: "AES-GCM", length: 256 },
        true,
        ["encrypt", "decrypt"]
      )
      const exported = await crypto.subtle.exportKey("jwk", this.masterKey)
      await set("assembly_master_key", exported)
    }
    return this.masterKey
  }

  private async persist() {
    const key = await this.getMasterKey()
    const iv = crypto.getRandomValues(new Uint8Array(12))
    const encoded = new TextEncoder().encode(JSON.stringify(this.inMemoryKeys))
    
    const ciphertext = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      encoded
    )

    await set(DB_KEY, { iv, ciphertext })
  }

  private async loadPersisted() {
    const stored = await get<{ iv: Uint8Array; ciphertext: ArrayBuffer }>(DB_KEY)
    if (!stored) return

    try {
      const key = await this.getMasterKey()
      const decrypted = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: stored.iv },
        key,
        stored.ciphertext
      )
      const decoded = new TextDecoder().decode(decrypted)
      this.inMemoryKeys = JSON.parse(decoded)
    } catch (e) {
      console.error("Failed to decrypt keys", e)
      this.inMemoryKeys = {}
    }
  }

  private async clearPersisted() {
    await del(DB_KEY)
  }
}

export const globalVault = new KeyVault()
