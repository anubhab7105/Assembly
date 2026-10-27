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
  send(data: string) { void data }

  // Test helper to simulate server sending a message
  mockMessage(event: ProgressEvent) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(event) })
    }
  }
}

type GlobalWithMockSocket = typeof globalThis & { mockWs?: MockWebSocket }

/** Latest mock socket without `any` casts. */
function mockSocket(): MockWebSocket {
  const socket = (globalThis as GlobalWithMockSocket).mockWs
  if (!socket) throw new Error("Expected mock WebSocket to be created")
  return socket
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
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket
    vi.useFakeTimers()
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
    delete (globalThis as GlobalWithMockSocket).mockWs
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

    const mockWs = mockSocket()
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
    const mockWs = mockSocket()

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
    // Older local history records without a confidence field stay unknown;
    // they must not be promoted to a high-confidence result by the UI.
    expect(result.current.confidence).toBeNull()
    // No websocket for local runs.
    expect((globalThis as GlobalWithMockSocket).mockWs).toBeUndefined()
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
          resolved_disagreement_count: 3,
          verification: {
            agents: 3,
            families: 2,
            rounds: 1,
            disagreements_resolved: 3,
            sources_verified: 2,
          },
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
      familyCount: 2,
      resolvedDisagreementCount: 3,
      verification: {
        agents: 3,
        families: 2,
        rounds: 1,
        disagreements_resolved: 3,
        sources_verified: 2,
      },
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

  it("preserves completed verification metrics when reopening local history", async () => {
    vi.useRealTimers()
    const { storage } = await import("@/lib/storage")
    vi.mocked(storage.getHistory).mockResolvedValue({
      id: "local-metrics",
      question: "Q?",
      answer: "A.",
      status: "completed",
      created_at: new Date().toISOString(),
      minutes: 5,
      agentCount: 3,
      debateRounds: 2,
      providers: ["groq", "openrouter"],
      verification: {
        agents: 3,
        families: 2,
        rounds: 2,
        disagreements_resolved: 4,
        sources_verified: 3,
      },
      disagreements: [
        { id: "d1", agent_id: "a1", issue: "Conflicting premise", resolved: true },
        { id: "d2", agent_id: "a2", issue: "Missing citation", resolved: true },
      ],
    })

    const { result } = renderHook(() => useExecution("local-metrics"))

    await waitFor(() => {
      expect(result.current.status).toBe("completed")
    })
    expect(result.current.summary).toMatchObject({
      agentCount: 3,
      familyCount: 2,
      debateRounds: 2,
      resolvedDisagreementCount: 4,
      verification: { disagreements_resolved: 4, sources_verified: 3 },
    })
    expect(result.current.disagreements).toHaveLength(2)
  })

  it("keeps legacy history metrics unavailable when they were never persisted", async () => {
    vi.useRealTimers()
    const { storage } = await import("@/lib/storage")
    vi.mocked(storage.getHistory).mockResolvedValue({
      id: "local-legacy",
      question: "Q?",
      answer: "A.",
      status: "completed",
      created_at: new Date().toISOString(),
      minutes: 3,
    })

    const { result } = renderHook(() => useExecution("local-legacy"))

    await waitFor(() => {
      expect(result.current.status).toBe("completed")
    })
    expect(result.current.summary?.agentCount).toBeNull()
    expect(result.current.summary?.familyCount).toBeNull()
    expect(result.current.summary?.debateRounds).toBeNull()
    expect(result.current.summary?.resolvedDisagreementCount).toBeNull()
  })
})
