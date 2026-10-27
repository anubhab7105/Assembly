import { describe, expect, it, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { FinalAnswer } from "./final-answer"
import type { ExecutionState } from "@/hooks/use-execution"

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

function makeState(confidence: ExecutionState["confidence"]): ExecutionState {
  return {
    status: "completed",
    connectionState: "connected",
    team: [],
    consensusScore: 0.9,
    consensusHistory: [],
    disagreements: [],
    sources: [],
    timerSeconds: null,
    finalAnswer: "The answer is available.",
    confidence,
    uncertaintyNote: null,
    question: "What is the answer?",
    attachments: [],
    round: 1,
    degradedMode: false,
    quotaWarning: null,
    feed: [],
    summary: null,
  }
}

describe("FinalAnswer confidence display", () => {
  it.each([
    { confidence: "High" as const, expectedClass: "bg-success/20" },
    { confidence: "Moderate" as const, expectedClass: "bg-warning/20" },
    { confidence: "Low" as const, expectedClass: "bg-danger/20" },
  ])("renders an explicitly assessed $confidence confidence", ({ confidence, expectedClass }) => {
    render(<FinalAnswer state={makeState(confidence)} />)

    const label = screen.getByTestId("confidence-label")
    expect(label.textContent).toContain(`Confidence: ${confidence}`)
    expect(label.getAttribute("data-confidence")).toBe(confidence)
    expect(label.className).toContain(expectedClass)
    expect(label.getAttribute("aria-label")).toContain(`Confidence assessment: ${confidence}`)
  })

  it("renders persisted metrics for completed investigations", () => {
    const state = makeState("Moderate")
    state.team = []
    state.round = 0
    state.disagreements = []
    state.summary = {
      agentCount: 3,
      providers: ["groq", "openrouter"],
      debateRounds: 2,
      tokens: 1200,
      elapsedSeconds: 42,
      modelFamilies: null,
      familyCount: 2,
      resolvedDisagreementCount: 4,
      verification: {
        agents: 3,
        families: 2,
        rounds: 2,
        disagreements_resolved: 4,
        sources_verified: 3,
      },
    }

    render(<FinalAnswer state={state} />)
    fireEvent.click(screen.getByTestId("confidence-label"))

    expect(screen.getByText("3 Agents")).toBeDefined()
    expect(screen.getByText("2 Model Families")).toBeDefined()
    expect(screen.getByText("2 Debate Rounds")).toBeDefined()
    expect(screen.getByText("Unavailable")).toBeDefined()
  })

  it("shows unavailable rather than fabricated zeroes for legacy completed runs", () => {
    const state = makeState(null)
    state.team = []
    state.round = 0
    state.summary = {
      agentCount: null,
      providers: null,
      debateRounds: null,
      tokens: null,
      elapsedSeconds: null,
      modelFamilies: null,
      familyCount: null,
      resolvedDisagreementCount: null,
      verification: null,
    }

    render(<FinalAnswer state={state} />)
    fireEvent.click(screen.getByTestId("confidence-label"))

    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(4)
    expect(screen.queryByText("0 Agents")).toBeNull()
    expect(screen.queryByText("0 Debate Rounds")).toBeNull()
  })

  it("renders missing confidence as a neutral, accessible Not assessed state", () => {
    render(<FinalAnswer state={makeState(null)} />)

    const label = screen.getByTestId("confidence-label")
    expect(label.textContent).toContain("Confidence: Not assessed")
    expect(label.getAttribute("data-confidence")).toBe("unknown")
    expect(label.className).toContain("text-muted-foreground")
    expect(label.className).toContain("border-border")
    expect(label.className).not.toContain("bg-success/20")
    expect(label.getAttribute("aria-label")).toContain("Confidence assessment: Not assessed")
    expect(label.getAttribute("aria-expanded")).toBe("false")

    fireEvent.click(label)
    expect(label.getAttribute("aria-expanded")).toBe("true")
    expect(screen.getByText("Team Size")).toBeDefined()
  })
})
