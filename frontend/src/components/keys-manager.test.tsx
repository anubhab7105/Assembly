import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { KeysManager } from "./keys-manager";
import { ToastProvider } from "./ui/toast";
import { ApiClient } from "@/lib/api-client";

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
    remember: false,
    unlocked: false,
    setRemember: vi.fn(),
    setKey: vi.fn(),
    allKeys: vi.fn().mockResolvedValue({}),
    clearAll: vi.fn(),
    unlock: vi.fn(),
  },
}));

const catalogFixture = {
  providers: [
    {
      id: "groq",
      enabled: true,
      key_url: "https://console.groq.com/keys",
      privacy_note: null,
      key_steps: ["Open the key page.", "Sign in.", "Press Test."],
      key_notes: null,
      sensitive_signup: null,
      models: [
        { id: "openai/gpt-oss-20b", family: "gpt-oss", roles: ["solver"], scope: "model" },
      ],
    },
    {
      id: "openrouter",
      enabled: true,
      key_url: "https://openrouter.ai/keys",
      privacy_note: null,
      key_steps: ["Open the key page.", "Create a key."],
      key_notes: null,
      sensitive_signup: null,
      models: [{ id: "x:free", family: "gemma", roles: ["solver"], scope: "account" }],
    },
  ],
  families: ["gemma", "gpt-oss"],
  recommended_order: ["groq", "openrouter"],
  minimum_families: 3,
  sensitive_signup_fallback:
    "Check this during signup; if it asks for payment, skip this provider (Assembly is free-tier only)",
};

beforeEach(() => {
  vi.mocked(ApiClient.catalog).mockResolvedValue(catalogFixture as never);
  vi.mocked(ApiClient.wakeup).mockResolvedValue(undefined);
});

describe("KeysManager setup page (FR-30 snapshot)", () => {
  it("shows banner, stepper, copy-link, hint, why line and fallback", async () => {
    const { container } = render(
      <ToastProvider>
        <KeysManager />
      </ToastProvider>,
    );
    expect(await screen.findByTestId("minimum-to-start-banner")).toBeDefined();
    expect((await screen.findByTestId("minimum-to-start-text")).textContent).toContain(
      "3 model families",
    );
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
    // (2 catalog providers + the standalone Tavily search-key card).
    expect(container.querySelectorAll("[data-testid^='provider-card-']").length).toBe(3);
    expect(await screen.findByTestId("provider-card-tavily")).toBeDefined();
    expect((await screen.findByTestId("provider-card-tavily")).textContent).toContain(
      "keyless sources",
    );
    expect(await screen.findByTestId("tavily-input")).toBeDefined();
    expect(await screen.findByTestId("tavily-save")).toBeDefined();
  });
});
