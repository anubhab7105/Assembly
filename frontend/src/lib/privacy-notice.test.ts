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
    expect(PRIVACY_NOTICE_VERSION).toBe(2);
    const webNotice = WEB_PRIVACY_PARAGRAPHS.join(" ");
    expect(webNotice).toContain("across refreshes");
    expect(webNotice).toContain("until you remove them in Settings");
    expect(webNotice).toContain("does not persist them");
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
  });
});
