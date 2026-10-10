/**
 * KeyVault unit tests: save, reload, unlock, wrong passphrase, forget.
 * idb-keyval is mocked with an in-memory Map (jsdom has no IndexedDB);
 * WebCrypto does the real PBKDF2/AES-GCM work. Canary strings only.
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

import { KeyVault } from "./key-vault";

const CANARY_A = "gsk-CANARY-VAULT-A1";
const CANARY_B = "tvly-CANARY-VAULT-B2";
const PASS = "test-passphrase-01";

function mockLocalStorage() {
  const bag = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => bag.get(k) ?? null,
    setItem: (k: string, v: string) => void bag.set(k, v),
    removeItem: (k: string) => void bag.delete(k),
  } as Storage);
}

describe("KeyVault", () => {
  beforeEach(() => {
    store.clear();
    mockLocalStorage();
  });

  it("keeps saved keys in memory only by default", async () => {
    const vault = new KeyVault();
    await vault.setKey("groq", CANARY_A);
    expect(await vault.allKeys()).toEqual({ groq: CANARY_A });
    expect(store.size).toBe(0);
  });

  it("reload without unlock yields nothing but keeps the blob", async () => {
    const first = new KeyVault();
    first.setRemember(true);
    first.unlock(PASS);
    await first.setKey("groq", CANARY_A);
    expect(store.size).toBe(1);

    const reloaded = new KeyVault();
    reloaded.setRemember(true);
    expect(await reloaded.hasPersisted()).toBe(true);
    // Locked: nothing readable, blob untouched.
    expect(await reloaded.allKeys()).toEqual({});
    expect(store.size).toBe(1);
  });

  it("unlock with the passphrase restores keys", async () => {
    const first = new KeyVault();
    first.setRemember(true);
    first.unlock(PASS);
    await first.setKey("groq", CANARY_A);
    await first.setKey("tavily", CANARY_B);

    const reloaded = new KeyVault();
    reloaded.setRemember(true);
    reloaded.unlock(PASS);
    expect(await reloaded.allKeys()).toEqual({ groq: CANARY_A, tavily: CANARY_B });
  });

  it("wrong passphrase shows an error and deletes nothing", async () => {
    const first = new KeyVault();
    first.setRemember(true);
    first.unlock(PASS);
    await first.setKey("groq", CANARY_A);

    const reloaded = new KeyVault();
    reloaded.setRemember(true);
    reloaded.unlock("wrong-passphrase-99");
    await expect(reloaded.allKeys()).rejects.toThrow(/Wrong passphrase/);
    // Blob intact for a later correct attempt.
    expect(store.size).toBe(1);
    reloaded.unlock(PASS);
    expect(await reloaded.allKeys()).toEqual({ groq: CANARY_A });
  });

  it("forget clears memory and disk, and disables remember", async () => {
    const vault = new KeyVault();
    vault.setRemember(true);
    vault.unlock(PASS);
    await vault.setKey("groq", CANARY_A);
    await vault.clearAll();
    expect(await vault.allKeys()).toEqual({});
    expect(await vault.hasPersisted()).toBe(false);
    expect(vault.remember).toBe(false);
  });
});
