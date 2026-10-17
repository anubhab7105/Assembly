import { afterEach, describe, expect, it, vi } from "vitest"
import { ApiClient } from "./api-client"

function installStreamFetch() {
  const encoder = new TextEncoder()
  const chunks = [
    `data: ${JSON.stringify({ event_type: "execution.completed", data: { answer: "ok" } })}\n\n`,
    `data: ${JSON.stringify({ event_type: "run.finished", status: "completed", usage: [] })}\n\n`,
  ].map((chunk) => encoder.encode(chunk))
  let index = 0
  const fetchSpy = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    body: {
      getReader() {
        return {
          async read() {
            if (index >= chunks.length) return { done: true, value: undefined }
            return { done: false, value: chunks[index++] }
          },
        }
      },
    },
  })
  global.fetch = fetchSpy as unknown as typeof fetch
  return fetchSpy
}

afterEach(() => vi.restoreAllMocks())

const baseArgs = {
  question: "Review these files",
  minutes: 3,
  providerKeys: { groq: "test-only-key" },
  selection: { selected: [], pins: {} },
  usage: [],
}

describe("ApiClient attachment payload", () => {
  it("sends text attachments with a run without modifying the original question", async () => {
    const fetchSpy = installStreamFetch()
    const attachments = [
      { filename: "notes.md", media_type: "text/markdown", content: "PRIVATE-TEST-CONTENT-CANARY" },
    ]
    await ApiClient.startRunStream({ ...baseArgs, attachments }, () => {})
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit
    const payload = JSON.parse(String(init.body))
    expect(payload.question).toBe(baseArgs.question)
    expect(payload.attachments).toEqual(attachments)
  })

  it("omits attachments from a run payload when none are selected", async () => {
    const fetchSpy = installStreamFetch()
    await ApiClient.startRunStream(baseArgs, () => {})
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit
    const payload = JSON.parse(String(init.body))
    expect(payload).not.toHaveProperty("attachments")
  })
})
