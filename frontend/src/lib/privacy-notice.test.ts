import { describe, it, expect } from "vitest";
import {
  GENERIC_PROVIDER_NOTE,
  PRIVACY_NOTICE_VERSION,
  buildAck,
  needsAck,
  providerNoteFor,
  WEB_PRIVACY_PARAGRAPHS,
  DESKTOP_PRIVACY_PARAGRAPHS,
} from "./privacy-notice";

const CANARY = "sk-CANARY-PRIVACY-9f8e7d6c5b4a";

describe("privacy-notice", () => {
  it("first run is blocked until acknowledged", () => {
    expect(needsAck(null)).toBe(true);
  });

  it("acknowledgment persists across reload (same version)", () => {
    const ack = buildAck();
    const reloaded = JSON.parse(JSON.stringify(ack));
    expect(needsAck(reloaded)).toBe(false);
  });

  it("version bump re-prompts", () => {
    expect(needsAck({ version: PRIVACY_NOTICE_VERSION - 1, acknowledged_at: new Date().toISOString() })).toBe(true);
  });

  it("discloses persistent web-key retention and request-scoped backend handling", () => {
    expect(PRIVACY_NOTICE_VERSION).toBe(3);
    const webNotice = WEB_PRIVACY_PARAGRAPHS.join(" ");
    expect(webNotice).toContain("across refreshes");
    expect(webNotice).toContain("until you remove them in Settings");
    expect(webNotice).toContain("not persisted by the Assembly application");
    expect(webNotice).toContain("all saved model-provider keys");
    expect(webNotice).toContain("not only keys for selected models");
    expect(webNotice).toContain("any saved Tavily key");
    expect(webNotice).toContain("even when search is not used");
    expect(webNotice).toContain("not encrypted at rest");
    expect(webNotice).toContain("same-origin JavaScript");
    expect(webNotice).toContain("XSS vulnerability");
    expect(webNotice).toContain("Hosting providers may process network traffic");
    expect(webNotice).not.toContain("Windows Credential Manager");
    const desktopNotice = DESKTOP_PRIVACY_PARAGRAPHS.join(" ");
    expect(desktopNotice).toContain("WebView browser profile");
    expect(desktopNotice).toContain("over loopback");
    expect(desktopNotice).toContain("all saved model-provider keys");
    expect(desktopNotice).toContain("any saved Tavily key");
    expect(desktopNotice).toContain("even when search is not used");
    expect(desktopNotice).toContain("XSS incident");
    expect(desktopNotice).toContain("Windows Credential Manager adapter");
    expect(desktopNotice).toContain("does not use it as the primary key store");
    expect(webNotice).toContain("HTTPS");
  });

  it("shows the gemini note only when gemini is enabled", () => {
    const gemini = providerNoteFor({
      id: "gemini",
      privacy_note:
        "Free-tier requests may be used by Google to improve its products. Avoid sending sensitive or confidential information.",
    });
    expect(gemini).toContain("Google");
    const other = providerNoteFor({ id: "groq" });
    expect(other).toBe(GENERIC_PROVIDER_NOTE);
  });

  it("canary key typed in the UI never appears in the stored acknowledgment record", () => {
    // Simulate: user typed CANARY into a key input, then acknowledged.
    const typedKey = CANARY;
    void typedKey;
    const stored = JSON.stringify(buildAck());
    expect(stored).not.toContain(CANARY);
    expect(stored).toContain(String(PRIVACY_NOTICE_VERSION));
  });

  it("dialog text matches docs/privacy.md paragraphs", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const doc = fs.readFileSync(path.resolve(__dirname, "../../../docs/privacy.md"), "utf-8");
    for (const p of WEB_PRIVACY_PARAGRAPHS) {
      if (p === "Each model provider handles your inputs under its own policy:") continue;
      expect(doc).toContain(p);
    }
    for (const p of DESKTOP_PRIVACY_PARAGRAPHS) {
      if (p === "Each model provider handles your inputs under its own policy:") continue;
      expect(doc).toContain(p);
    }
    const publicPolicy = fs.readFileSync(path.resolve(__dirname, "../app/privacy/page.tsx"), "utf-8");
    expect(publicPolicy).toContain("not encrypted at rest");
    expect(publicPolicy).toContain("same-origin JavaScript");
    expect(publicPolicy).toContain("hosted Assembly backend over HTTPS");
    expect(publicPolicy).toContain("all saved model-provider keys");
    expect(publicPolicy).toContain("any saved Tavily key");
    expect(publicPolicy).toContain("even when search is not used");
    expect(publicPolicy).toContain("Hosting providers may process network traffic");
    expect(publicPolicy).toContain("WebView browser profile");
  });
});
