import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"
import { useExecution } from "./use-execution"
import type { ProgressEvent } from "@/lib/events"

// Mock WebSocket
class MockWebSocket {
  url: string
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onopen: (() => void) | null = null
  readyState: number = WebSocket.OPEN

  constructor(url: string) {
    this.url = url
    // Expose the mock instance globally for tests to emit messages
    ;(globalThis as unknown as Record<string, MockWebSocket>).mockWs = this
  }

  close() {}
  send(_data: string) {}

  // Test helper to simulate server sending a message
  mockMessage(event: ProgressEvent) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(event) })
    }
  }
}

/** Latest mock socket without `any` casts. */
function mockSocket(): MockWebSocket {
  return (globalThis as unknown as Record<string, MockWebSocket>).mockWs
}

vi.mock("@/lib/env", () => ({
  env: { apiUrl: "http://localhost:8000", NEXT_PUBLIC_APP_MODE: "dev", desktopToken: "" },
}))

vi.mock("@/lib/storage", () => ({
  storage: {
    getHistory: vi.fn().mockResolvedValue(null),
    listHistory: vi.fn().mockResolvedValue([]),
  },
}))

describe("useExecution hook", () => {
  let originalWebSocket: typeof WebSocket

  beforeEach(() => {
    originalWebSocket = globalThis.WebSocket
    globalThis.WebSocket = MockWebSocket as any
    vi.useFakeTimers()
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
    delete (globalThis as any).mockWs
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it("initializes with idle state", () => {
    const { result } = renderHook(() => useExecution(null))
    expect(result.current.status).toBe("idle")
    expect(result.current.team).toEqual([])
  })

  it("connects to websocket and updates state on team.ready", () => {
    const { result } = renderHook(() => useExecution("exec_123"))

    const mockWs = (globalThis as any).mockWs as MockWebSocket
    expect(mockWs).toBeDefined()
    expect(mockWs.url).toContain("ws://localhost:8000/api/executions/ws/exec_123")

    act(() => {
      mockWs.mockMessage({
        event_type: "team.ready",
        execution_id: "exec_123",
        seq: 1,
        state: "running",
        timestamp: new Date().toISOString(),
        data: {
          agents: [{ id: "a1", role: "Critic", model_family: "gemini" }]
        }
      })
    })

    expect(result.current.status).toBe("running")
    expect(result.current.team).toHaveLength(1)
    expect(result.current.team[0].model_family).toBe("gemini")
  })

  it("handles out-of-order/duplicate events (seq filtering)", () => {
    const { result } = renderHook(() => useExecution("exec_123"))
    const mockWs = (globalThis as any).mockWs as MockWebSocket

    act(() => {
      mockWs.mockMessage({
        event_type: "team.ready",
        execution_id: "exec_123",
        seq: 2, // sequence 2
        state: "running",
        timestamp: new Date().toISOString(),
        data: { agents: [] }
      })
    })

    expect(result.current.status).toBe("running")

    act(() => {
      // Re-send seq 1 (older than current lastSeq of 2)
      mockWs.mockMessage({
        event_type: "execution.started",
        execution_id: "exec_123",
        seq: 1,
        state: "starting",
        timestamp: new Date().toISOString(),
        data: {}
      })
    })

    // Status should NOT revert to starting
    expect(result.current.status).toBe("running")
  })

  it("loads local stateless runs from device storage without a socket", async () => {
    vi.useRealTimers()
    const { storage } = await import("@/lib/storage")
    vi.mocked(storage.getHistory).mockResolvedValue({
      id: "local-1",
      question: "What is stored?",
      answer: "Stored answer",
      status: "completed",
      created_at: new Date().toISOString(),
      minutes: 3,
      consensus: 0.9,
    })

    const { result } = renderHook(() => useExecution("local-1"))

    await waitFor(() => {
      expect(result.current.question).toBe("What is stored?")
    })
    expect(result.current.finalAnswer).toBe("Stored answer")
    // No websocket for local runs.
    expect((globalThis as any).mockWs).toBeUndefined()
  })

  it("maps backend wire names on execution.completed (answer/confidence_label)", () => {
    const { result } = renderHook(() => useExecution("exec_123"))
    const mockWs = mockSocket()

    act(() => {
      mockWs.mockMessage({
        event_type: "execution.completed",
        execution_id: "exec_123",
        seq: 1,
        state: "completed",
        timestamp: new Date().toISOString(),
        data: {
          answer: "The team concludes 42.",
          confidence_label: "Moderate",
          consensus_score: 0.64,
          agent_count: 3,
          providers_used: ["groq", "openrouter"],
          debate_rounds: 1,
          tokens_used: 7000,
          elapsed_seconds: 35.7,
        },
      })
    })

    // Chip label comes from the capped server label, matching the
    // "Confidence:" line the composer writes into the answer.
    expect(result.current.finalAnswer).toBe("The team concludes 42.")
    expect(result.current.confidence).toBe("Moderate")
    expect(result.current.summary).toMatchObject({
      agentCount: 3,
      providers: ["groq", "openrouter"],
      debateRounds: 1,
      tokens: 7000,
      elapsedSeconds: 35.7,
    })
  })

  it("hydrates confidence and summary from device history", async () => {
    vi.useRealTimers()
    const { storage } = await import("@/lib/storage")
    vi.mocked(storage.getHistory).mockResolvedValue({
      id: "local-2",
      question: "Q?",
      answer: "A.",
      status: "completed",
      created_at: new Date().toISOString(),
      minutes: 5,
      consensus: 0.64,
      confidence: "Moderate",
      agentCount: 3,
      providers: ["groq"],
      debateRounds: 1,
      tokens: 7000,
      elapsedSeconds: 35.7,
    })

    const { result } = renderHook(() => useExecution("local-2"))

    await waitFor(() => {
      expect(result.current.confidence).toBe("Moderate")
    })
    expect(result.current.summary).toMatchObject({ agentCount: 3, tokens: 7000 })
  })
})
