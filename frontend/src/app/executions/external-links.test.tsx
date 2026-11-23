/** @vitest-environment jsdom */

import React from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import ExecutionPage from "@/app/executions/page"

const { mockUseExecution } = vi.hoisted(() => ({
  mockUseExecution: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("id=run-test"),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>{children}</a>
  ),
}))

vi.mock("@/hooks/use-execution", () => ({
  useExecution: mockUseExecution,
}))

vi.mock("@/components/cinematic/comfort", () => ({
  useComfort: () => ({ settings: { sourcesFirst: false } }),
}))

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

const sourceHref = "https://source.example/article"
const markdownHref = "https://docs.example/guide"

beforeEach(() => {
  mockUseExecution.mockReturnValue({
    status: "completed",
    connectionState: "connected",
    team: [],
    consensusScore: null,
    consensusHistory: [],
    disagreements: [],
    sources: [
      {
        id: "source-1",
        url: sourceHref,
        title: "Source article",
        verified: true,
      },
    ],
    timerSeconds: null,
    finalAnswer: "[External guide](https://docs.example/guide)",
    confidence: "Moderate",
    uncertaintyNote: null,
    question: null,
    attachments: [],
    round: 0,
    degradedMode: false,
    quotaWarning: null,
    feed: [],
    summary: null,
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("ExecutionContent external links", () => {
  it("renders the source link with safe external link attributes", () => {
    render(<ExecutionPage />)

    const link = screen
    .getAllByRole("link", { name: "[1] Source article" })
    .find((element) => element.getAttribute("href") === sourceHref)

    expect(link?.getAttribute("href")).toBe(sourceHref)
    expect(link?.getAttribute("target")).toBe("_blank")

    const rel = link?.getAttribute("rel")?.split(/\s+/) ?? []
    expect(rel).toEqual(
    expect.arrayContaining(["noopener", "noreferrer"])
    )
  })

  it("renders external Markdown links with safe attributes", () => {
    render(<ExecutionPage />)

    const link = screen.getByRole("link", { name: "External guide" })

    expect(link.getAttribute("href")).toBe(markdownHref)
    expect(link.getAttribute("target")).toBe("_blank")
    expect(link.getAttribute("rel")?.split(/\s+/)).toEqual(
      expect.arrayContaining(["noopener", "noreferrer"]),
    )
  })
})