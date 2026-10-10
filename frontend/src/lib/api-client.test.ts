import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApiClient } from "./api-client";

function mockFetchOnce(payload: unknown, ok = true, status = 200) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: () => Promise.resolve(payload),
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("ApiClient.testKey UI states", () => {
  it("maps valid list probes to valid", async () => {
    mockFetchOnce({ valid: true, rate_limited: false, error_code: null, message: "Key verified for gemini." });
    const res = await ApiClient.testKey("gemini", "k");
    expect(res.status).toBe("valid");
    expect(res.message).toContain("verified");
  });

  it("maps 400 API_KEY_INVALID / 401 / 403 to invalid", async () => {
    for (const code of ["auth_error"]) {
      mockFetchOnce({ valid: false, rate_limited: false, error_code: code, message: "Key was rejected." });
      const res = await ApiClient.testKey("gemini", "k");
      expect(res.status).toBe("invalid");
    }
  });

  it("maps 429 to rate_limited with a key-is-valid message", async () => {
    mockFetchOnce({
      valid: false,
      rate_limited: true,
      error_code: "rate_limited",
      message: "Key is valid; quota or rate limit reached right now.",
    });
    const res = await ApiClient.testKey("gemini", "k");
    expect(res.status).toBe("rate_limited");
    expect(res.message).toContain("Key is valid");
  });

  it("maps 404 model to model_unavailable with alternatives", async () => {
    mockFetchOnce({
      valid: true,
      rate_limited: false,
      error_code: "model_not_found",
      message: "Key is valid; model gemini-3.8-flash is not available to this key.",
      available_models: ["gemini-2.0-flash"],
    });
    const res = await ApiClient.testKey("gemini", "k");
    expect(res.status).toBe("model_unavailable");
    expect(res.availableModels).toContain("gemini-2.0-flash");
  });

  it("maps timeouts to unreachable, never invalid", async () => {
    mockFetchOnce({
      valid: false,
      rate_limited: false,
      error_code: "unreachable",
      message: "Couldn't reach Google; try again.",
    });
    const res = await ApiClient.testKey("gemini", "k");
    expect(res.status).toBe("unreachable");
  });

  it("maps endpoint rate limits (HTTP 429) to rate_limited", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      statusText: "Too Many Requests",
      json: () => Promise.resolve({}),
    }) as unknown as typeof fetch;
    const res = await ApiClient.testKey("gemini", "k");
    expect(res.status).toBe("rate_limited");
  });

  it("maps network failures to unreachable, never invalid", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("fetch failed")) as unknown as typeof fetch;
    const res = await ApiClient.testKey("gemini", "k");
    expect(res.status).toBe("unreachable");
  });

  it("never surfaces key material in results", async () => {
    const canary = "sk-CANARY-9f8e7d6c5b4a";
    mockFetchOnce({ valid: false, rate_limited: false, error_code: "auth_error", message: "Key was rejected." });
    const res = await ApiClient.testKey("gemini", canary);
    expect(JSON.stringify(res)).not.toContain(canary);
    expect(document.body.innerHTML).not.toContain(canary);
  });
});
