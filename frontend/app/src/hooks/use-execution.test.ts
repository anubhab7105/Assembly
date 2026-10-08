import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"
import { useExecution } from "./use-execution"
import type { ProgressEvent } from "@/lib/events"
import { ApiClient } from "@/lib/api-client"

// Mock WebSocket
class MockWebSocket {
  url: string
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  readyState: number = WebSocket.OPEN
  
  constructor(url: string) {
    this.url = url
    // Expose the mock instance globally for tests to emit messages
    ;(globalThis as any).mockWs = this
  }
  
  close() {}
  
  // Test helper to simulate server sending a message
  mockMessage(event: ProgressEvent) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(event) })
    }
  }
}

vi.mock("@/lib/env", () => ({
  env: { apiUrl: "http://localhost:8000" }
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
    expect(mockWs.url).toContain("ws://localhost:8000/executions/exec_123/ws")

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

  it("falls back to REST API polling when WebSocket fails repeatedly", async () => {
    const mockGetExecution = vi.spyOn(ApiClient, "getExecution").mockResolvedValue({
      id: "exec_123",
      status: "completed",
      events: []
    })

    const { result } = renderHook(() => useExecution("exec_123"))
    let mockWs = (globalThis as any).mockWs as MockWebSocket

    // Simulate 5 connection failures (WS_RECONNECT_MAX_ATTEMPTS)
    for (let i = 0; i <= 5; i++) {
      act(() => {
        if (mockWs.onclose) mockWs.onclose()
      })
      // Fast forward the reconnect delay (2000ms * attempt)
      act(() => {
        vi.runAllTimers()
      })
      mockWs = (globalThis as any).mockWs as MockWebSocket
    }

    // After 5 failures, it should start polling (every 5 seconds)
    act(() => {
      vi.advanceTimersByTime(5000)
    })

    await waitFor(() => {
      expect(mockGetExecution).toHaveBeenCalledWith("exec_123")
      expect(result.current.status).toBe("completed")
    })
  })
})
