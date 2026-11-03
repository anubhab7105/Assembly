import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { ExecutionTiming } from "./execution-timing"

describe("ExecutionTiming", () => {
  it("renders the remaining estimate for an active run", () => {
    const { container } = render(
      <ExecutionTiming status="solving" remainingSeconds={95} elapsedSeconds={20} />,
    )

    expect(screen.getByTestId("execution-timing-label").textContent).toBe("Time Remaining")
    expect(container.textContent).toContain("1:35")
  })

  it("renders elapsed time, not a stale countdown, for completed runs", () => {
    const { container } = render(
      <ExecutionTiming status="completed" remainingSeconds={12} elapsedSeconds={42.4} />,
    )

    expect(screen.getByTestId("execution-timing-label").textContent).toBe("Elapsed")
    expect(container.textContent).toContain("0:42")
    expect(container.textContent).not.toContain("0:12")
  })

  it("uses duration wording for cancelled runs", () => {
    const { container } = render(
      <ExecutionTiming status="cancelled" remainingSeconds={30} elapsedSeconds={18} />,
    )

    expect(screen.getByTestId("execution-timing-label").textContent).toBe("Duration")
    expect(container.textContent).toContain("0:18")
  })

  it.each(["failed", "failed_partial"])("uses duration wording for %s runs", (status) => {
    const { container } = render(
      <ExecutionTiming status={status} remainingSeconds={30} elapsedSeconds={21} />,
    )

    expect(screen.getByTestId("execution-timing-label").textContent).toBe("Duration")
    expect(container.textContent).toContain("0:21")
  })

  it("shows unavailable when active or unknown runs have no trustworthy timing value", () => {
    const { rerender, container } = render(
      <ExecutionTiming status="planning" remainingSeconds={null} elapsedSeconds={null} />,
    )

    expect(screen.getByTestId("execution-timing-label").textContent).toBe("Time Unavailable")
    expect(container.textContent).toContain("Unavailable")

    rerender(
      <ExecutionTiming status="unknown" remainingSeconds={90} elapsedSeconds={null} />,
    )

    expect(screen.getByTestId("execution-timing-label").textContent).toBe("Time Unavailable")
    expect(container.textContent).toContain("Unavailable")
    expect(container.textContent).not.toContain("1:30")
  })

  it("does not invent a duration when terminal timing data is missing", () => {
    const { container } = render(
      <ExecutionTiming status="failed" remainingSeconds={90} elapsedSeconds={null} />,
    )

    expect(screen.getByTestId("execution-timing-label").textContent).toBe("Duration")
    expect(container.textContent).toContain("Unavailable")
    expect(container.textContent).not.toContain("1:30")
  })
})
