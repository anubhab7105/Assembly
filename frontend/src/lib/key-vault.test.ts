/**
 * KeyVault regression tests for the P0 refresh bug.
 *
 * The old vault kept keys in memory unless Remember+passphrase was set, so
 * every plain Save vanished on reload. These tests pin the fixed contract:
 * save → new instance (simulated reload) → restored, with merge/remove/
 * honest-failure semantics. idb-keyval is mocked with an in-memory Map
 * shared across instances (jsdom has no IndexedDB); WebCrypto does real
 * work only for the legacy-migration roundtrip. Canary strings only.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const store = new Map<string, unknown>();

vi.mock("idb-keyval", () => ({
  get: vi.fn((key: string) => Promise.resolve(store.get(key))),
  set: vi.fn((key: string, value: unknown) => {
    store.set(key, value);
    return Promise.resolve();
  }),
  del: vi.fn((key: string) => {
    store.delete(key);
    return Promise.resolve();
  }),
}));

import { get, set } from "idb-keyval";
import { KeyVault, KeyStorageError, KEYS_STORE_KEY } from "./key-vault";

const CANARY_A = "gsk-CANARY-VAULT-A1";
const CANARY_B = "tvly-CANARY-VAULT-B2";
const CANARY_C = "sk-or-CANARY-VAULT-C3";
const PASS = "test-passphrase-01";

function mockLocalStorage() {
  const bag = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => bag.get(k) ?? null,
    setItem: (k: string, v: string) => void bag.set(k, v),
    removeItem: (k: string) => void bag.delete(k),
  } as Storage);
  return bag;
}

async function buildLegacyBlob(passphrase: string, keys: Record<string, string>) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const base = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  const kek = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: salt as BufferSource, iterations: 210_000, hash: "SHA-256" },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv as BufferSource },
    kek,
    new TextEncoder().encode(JSON.stringify(keys)),
  );
  const b64 = (buf: ArrayBuffer | Uint8Array) => {
    const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    let s = "";
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s);
  };
  await set("assembly_keys_encrypted_v2", {
    v: 2,
    salt: b64(salt),
    iv: b64(iv),
    ciphertext: b64(ciphertext),
  });
}

describe("KeyVault persistence (P0)", () => {
  beforeEach(() => {
    store.clear();
    mockLocalStorage();
    vi.mocked(get).mockImplementation((key: Parameters<typeof get>[0]) => Promise.resolve(store.get(key as string)));
    vi.mocked(set).mockImplementation((key: Parameters<typeof set>[0], value: unknown) => {
      store.set(key as string, value);
      return Promise.resolve();
    });
  });

  it("1. save restores after reload with no extra step", async () => {
    const first = new KeyVault();
    await first.setKey("groq", CANARY_A);
    expect(await first.hasPersisted()).toBe(true);

    const reloaded = new KeyVault();
    expect(await reloaded.allKeys()).toEqual({ groq: CANARY_A });
    expect(await reloaded.getKey("groq")).toBe(CANARY_A);
  });

  it("2. multiple providers all survive reload", async () => {
    const first = new KeyVault();
    await first.setKey("groq", CANARY_A);
    await first.setKey("tavily", CANARY_B);
    await first.setKey("openrouter", CANARY_C);

    const reloaded = new KeyVault();
    expect(await reloaded.allKeys()).toEqual({
      groq: CANARY_A,
      tavily: CANARY_B,
      openrouter: CANARY_C,
    });
  });

  it("uses persistent localStorage fallback if IndexedDB is unavailable and clears it on deletion", async () => {
    const fallback = mockLocalStorage();
    vi.mocked(get).mockRejectedValue(new Error("IndexedDB unavailable"));
    vi.mocked(set).mockRejectedValue(new Error("IndexedDB unavailable"));

    const vault = new KeyVault();
    await vault.setKey("groq", CANARY_A);
    expect(JSON.parse(fallback.get("assembly:keys_v1") ?? "{}")).toEqual({ groq: CANARY_A });

    const reloaded = new KeyVault();
    expect(await reloaded.allKeys()).toEqual({ groq: CANARY_A });

    await reloaded.removeKey("groq");
    expect(await new KeyVault().allKeys()).toEqual({});
  });

  it("3. initialization never overwrites pre-existing values with empty defaults", async () => {
    await set(KEYS_STORE_KEY, { groq: CANARY_A });
    const fresh = new KeyVault();
    // No write performed — a pure read must return the saved value.
    expect(await fresh.allKeys()).toEqual({ groq: CANARY_A });
    expect(store.get(KEYS_STORE_KEY)).toEqual({ groq: CANARY_A });
  });

  it("5. updating one provider preserves the others", async () => {
    const vault = new KeyVault();
    await vault.setKey("groq", CANARY_A);
    await vault.setKey("tavily", CANARY_B);
    await vault.setKey("groq", CANARY_C);

    const reloaded = new KeyVault();
    expect(await reloaded.allKeys()).toEqual({ groq: CANARY_C, tavily: CANARY_B });
  });

  it("6. explicit per-provider removal keeps the others", async () => {
    const vault = new KeyVault();
    await vault.setKey("groq", CANARY_A);
    await vault.setKey("tavily", CANARY_B);
    await vault.removeKey("groq");

    expect(await vault.allKeys()).toEqual({ tavily: CANARY_B });
    const reloaded = new KeyVault();
    expect(await reloaded.allKeys()).toEqual({ tavily: CANARY_B });
  });

  it("clearAll removes memory and disk", async () => {
    const vault = new KeyVault();
    await vault.setKey("groq", CANARY_A);
    await vault.clearAll();
    expect(await vault.allKeys()).toEqual({});
    expect(await vault.hasPersisted()).toBe(false);
    const reloaded = new KeyVault();
    expect(await reloaded.allKeys()).toEqual({});
  });

  it("empty keys are rejected without claiming a save", async () => {
    const vault = new KeyVault();
    await expect(vault.setKey("groq", "   ")).rejects.toThrow(/Empty key/);
    expect(await vault.allKeys()).toEqual({});
    expect(await vault.hasPersisted()).toBe(false);
  });

  it("8. storage failure is surfaced honestly (nothing claimed saved)", async () => {
    const vault = new KeyVault();
    await vault.setKey("groq", CANARY_A);
    // Break both layers: IndexedDB get+set throw, localStorage throws.
    vi.mocked(get).mockRejectedValue(new Error("idb dead"));
    vi.mocked(set).mockRejectedValue(new Error("idb dead"));
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {
        throw new Error("quota exceeded");
      },
      removeItem: () => {},
    } as unknown as Storage);
    await expect(vault.setKey("tavily", CANARY_B)).rejects.toBeInstanceOf(KeyStorageError);
  });

  it("does not report removal as successful when both persistent stores reject writes", async () => {
    const vault = new KeyVault();
    await vault.setKey("groq", CANARY_A);

    vi.mocked(set).mockRejectedValue(new Error("IndexedDB unavailable"));
    vi.stubGlobal(
      "localStorage",
      {
        getItem: () => null,
        setItem: () => {
          throw new Error("storage unavailable");
        },
        removeItem: () => {},
      } as unknown as Storage,
    );

    await expect(vault.removeKey("groq")).rejects.toBeInstanceOf(KeyStorageError);
    expect(await new KeyVault().getKey("groq")).toBe(CANARY_A);
  });

  it("corrupt canonical record never crashes reads", async () => {
    await set(KEYS_STORE_KEY, { groq: 42 });
    const vault = new KeyVault();
    expect(await vault.allKeys()).toEqual({});
    expect(await vault.hasPersisted()).toBe(false);
  });

  it("legacy encrypted blob migrates once with the passphrase, then is gone", async () => {
    await buildLegacyBlob(PASS, { groq: CANARY_A });
    const vault = new KeyVault();
    expect(await vault.hasLegacyEncrypted()).toBe(true);
    // Canonical store is still empty: only the migration prompt should show.
    expect(await vault.allKeys()).toEqual({});
    await expect(vault.migrateLegacy("short")).rejects.toThrow(/at least 8/);
    await expect(vault.migrateLegacy("wrong-passphrase-99")).rejects.toThrow(/Wrong passphrase/);
    expect(await vault.hasLegacyEncrypted()).toBe(true);
    expect(await vault.migrateLegacy(PASS)).toEqual({ groq: CANARY_A });
    expect(await vault.hasLegacyEncrypted()).toBe(false);
    const reloaded = new KeyVault();
    expect(await reloaded.allKeys()).toEqual({ groq: CANARY_A });
  });
});
