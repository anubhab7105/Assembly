import { describe, it, expect } from "vitest";
import {
  SENSITIVE_SIGNUP_FALLBACK,
  isKeyFormatOk,
  keyPrefixHint,
  minimumToStartBanner,
  sensitiveSignupText,
  whyProviderLine,
} from "./key-setup";

describe("key-setup helpers (FR-30)", () => {
  it("nulls render the fallback text", () => {
    expect(sensitiveSignupText(null)).toBe(SENSITIVE_SIGNUP_FALLBACK);
    expect(sensitiveSignupText(undefined)).toBe(SENSITIVE_SIGNUP_FALLBACK);
    expect(sensitiveSignupText("")).toBe(SENSITIVE_SIGNUP_FALLBACK);
    expect(SENSITIVE_SIGNUP_FALLBACK).toContain("skip this provider");
  });

  it("prefix hint never blocks saving", () => {
    expect(isKeyFormatOk("groq", "anything")).toBe(true);
    expect(isKeyFormatOk("groq", "")).toBe(true);
    expect(isKeyFormatOk("unknown", "zzz")).toBe(true);
    expect(keyPrefixHint("groq")).toContain("paste");
  });

  it("why line derives from roles/families", () => {
    const line = whyProviderLine({
      id: "groq",
      models: [
        { family: "gpt-oss", roles: ["solver", "critic"] },
        { family: "qwen", roles: ["solver"] },
      ],
    });
    expect(line).toContain("gpt-oss");
    expect(line).toContain("qwen");
  });

  it("minimum banner mentions 3 families and recommended order", () => {
    const banner = minimumToStartBanner(1, ["groq", "openrouter", "gemini"]);
    expect(banner).toContain("3 model families");
    expect(banner).toContain("groq");
  });
});
