import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { KeysManager } from "./keys-manager";
import { ToastProvider } from "./ui/toast";
import { ApiClient } from "@/lib/api-client";
import { globalVault } from "@/lib/key-vault";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    ApiClient: {
      ...actual.ApiClient,
      wakeup: vi.fn(),
      catalog: vi.fn(),
      testKey: vi.fn(),
      clearAllKeys: vi.fn(),
    },
  };
});

vi.mock("@/lib/key-vault", () => ({
  globalVault: {
    setKey: vi.fn(),
    removeKey: vi.fn(),
    getKey: vi.fn(),
    allKeys: vi.fn().mockResolvedValue({}),
    hasPersisted: vi.fn().mockResolvedValue(false),
    hasLegacyEncrypted: vi.fn().mockResolvedValue(false),
    isUnlocked: vi.fn().mockReturnValue(false),
    unlock: vi.fn().mockResolvedValue({}),
    lock: vi.fn(),
    clearAll: vi.fn(),
  },
}));

const catalogFixture = {
  providers: [
    {
      id: "groq",
      enabled: true,
      limits_ready: true,
      key_url: "https://console.groq.com/keys",
      privacy_note: null,
      key_steps: ["Open the key page.", "Sign in.", "Press Test."],
      key_notes: null,
      sensitive_signup: null,
      models: [
        { id: "openai/gpt-oss-20b", family: "gpt-oss", roles: ["solver", "critic"], scope: "model" },
      ],
    },
    {
      id: "openrouter",
      enabled: true,
      limits_ready: true,
      key_url: "https://openrouter.ai/keys",
      privacy_note: null,
      key_steps: ["Open the key page.", "Create a key."],
      key_notes: null,
      sensitive_signup: null,
      models: [{ id: "x:free", family: "gemma", roles: ["solver", "critic"], scope: "account" }],
    },
  ],
  families: ["gemma", "gpt-oss"],
  recommended_order: ["groq", "openrouter"],
  minimum_families: 2,
  recommended_families: 3,
  sensitive_signup_fallback:
    "Check this during signup; if it asks for payment, skip this provider (Assembly is free-tier only)",
};

beforeEach(() => {
  vi.mocked(ApiClient.catalog).mockResolvedValue(catalogFixture as never);
  vi.mocked(ApiClient.wakeup).mockResolvedValue(undefined);
  vi.mocked(globalVault.isUnlocked).mockReturnValue(false);
  vi.mocked(globalVault.hasPersisted).mockResolvedValue(false);
  vi.mocked(globalVault.hasLegacyEncrypted).mockResolvedValue(false);
  vi.mocked(globalVault.allKeys).mockResolvedValue({});
  vi.mocked(globalVault.setKey).mockResolvedValue(undefined);
});

describe("KeysManager setup page (FR-30 snapshot)", () => {

  it("preserves the universal input when the locked vault rejects the save", async () => {
    const { container } = render(
      <ToastProvider>
        <KeysManager />
      </ToastProvider>,
    );
    const input = await screen.findByTestId("universal-save").then(() =>
      container.querySelector<HTMLInputElement>("#universal-key-input"),
    );
    if (!input) throw new Error("Universal key input was not rendered");
    fireEvent.change(input, { target: { value: "gsk-unlock-required-canary" } });
    fireEvent.click(screen.getByTestId("universal-save"));

    await waitFor(() => {
      expect(screen.getByTestId("unlock-error").textContent).toContain("Create or unlock");
    });
    expect(input.value).toBe("gsk-unlock-required-canary");
    expect(globalVault.setKey).not.toHaveBeenCalled();
  });

  it("clears provider, Tavily, and universal credential inputs when locking", async () => {
    vi.mocked(globalVault.isUnlocked).mockReturnValue(true);
    vi.mocked(globalVault.allKeys).mockResolvedValue({ groq: "gsk-saved-canary", tavily: "tvly-saved-canary" });
    const { container } = render(
      <ToastProvider>
        <KeysManager />
      </ToastProvider>,
    );

    const lock = await screen.findByTestId("lock-vault");
    const universal = container.querySelector<HTMLInputElement>("#universal-key-input");
    const tavily = screen.getByTestId("tavily-input") as HTMLInputElement;
    const provider = screen.getByTestId("provider-card-groq").querySelector<HTMLInputElement>('input[type="password"]');
    if (!universal || !provider) throw new Error("Credential input was not rendered");

    fireEvent.change(universal, { target: { value: "gsk-unsaved-universal" } });
    fireEvent.change(tavily, { target: { value: "tvly-unsaved-tavily" } });
    fireEvent.change(provider, { target: { value: "gsk-unsaved-provider" } });
    fireEvent.click(lock);

    expect(universal.value).toBe("");
    expect(tavily.value).toBe("");
    expect(provider.value).toBe("");
    expect(globalVault.lock).toHaveBeenCalled();
  });

  it("shows banner, stepper, copy-link, hint, why line and fallback", async () => {
    const { container } = render(
      <ToastProvider>
        <KeysManager />
      </ToastProvider>,
    );
    expect(await screen.findByTestId("minimum-to-start-banner")).toBeDefined();
    const readinessText = (await screen.findByTestId("minimum-to-start-text")).textContent ?? "";
    expect(readinessText).toContain("at least 2 distinct solver/critic model families");
    expect(readinessText).toContain("Three families are recommended");
    expect(await screen.findByTestId("stepper-groq")).toBeDefined();
    expect(await screen.findByTestId("copy-link-groq")).toBeDefined();
    expect((await screen.findByTestId("prefix-hint-groq")).textContent).toContain(
      "never blocks",
    );
    expect((await screen.findByTestId("why-groq")).textContent).toContain("gpt-oss");
    expect((await screen.findByTestId("signup-note-groq")).textContent).toContain(
      "skip this provider",
    );
    // Snapshot: stable rendered structure for the setup page
    // (6 model providers + the standalone Tavily search-key card).
    expect(container.querySelectorAll("[data-testid^='provider-card-']").length).toBe(7);
    expect(await screen.findByTestId("provider-card-tavily")).toBeDefined();
    expect((await screen.findByTestId("provider-card-tavily")).textContent).toContain(
      "keyless sources",
    );
    expect(await screen.findByTestId("tavily-input")).toBeDefined();
    expect(await screen.findByTestId("tavily-save")).toBeDefined();
    // Persistent vault: saved keys survive refresh; the legacy unlock
    // prompt appears only for pre-fix encrypted blobs.
    expect((await screen.findByTestId("persisted-banner")).textContent).toContain(
      "across refreshes",
    );
    expect(screen.getAllByText(/sent to the hosted Assembly backend over HTTPS.*preflight, key tests and runs/i)).toHaveLength(6);
    expect(screen.getByText(/saved Tavily key is sent to the hosted Assembly backend over HTTPS.*every run request, even when search is not used/i)).toBeDefined();
    expect(screen.queryByTestId("memory-only-banner")).toBeNull();
    expect(screen.queryByTestId("unlock-prompt")).toBeNull();
  });
});
