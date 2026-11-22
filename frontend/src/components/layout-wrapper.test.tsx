import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"

const listHistory = vi.fn()
const deleteHistory = vi.fn()
const importJSON = vi.fn()
const exportJSON = vi.fn()

vi.mock("@/lib/storage", () => ({
  storage: {
    listHistory: (...a: unknown[]) => listHistory(...a),
    deleteHistory: (...a: unknown[]) => deleteHistory(...a),
    importJSON: (...a: unknown[]) => importJSON(...a),
    exportJSON: (...a: unknown[]) => exportJSON(...a),
  },
}))
vi.mock("next/navigation", () => ({
  usePathname: () => "/executions",
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}))

import { SidebarContent } from "./layout-wrapper"
import { ToastProvider } from "@/components/ui/toast"

function renderSidebar() {
  return render(
    <ToastProvider>
      <SidebarContent />
    </ToastProvider>,
  )
}

describe("SidebarContent history loading", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, "error").mockImplementation(() => {})
  })

  it("shows the empty state for a successful empty read", async () => {
    listHistory.mockResolvedValue([])
    renderSidebar()
    expect(await screen.findByText("No saved investigations")).toBeTruthy()
    expect(screen.queryByTestId("history-load-error")).toBeNull()
  })

  it("shows a recoverable error, not the empty state, when the read fails", async () => {
    listHistory.mockRejectedValue(new Error("IndexedDB unavailable"))
    renderSidebar()
    const alert = await screen.findByTestId("history-load-error")
    expect(alert.textContent).toContain("Could not load history")
    expect(screen.queryByText("No saved investigations")).toBeNull()
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy()
  })

  it("retry re-reads history and recovers without mutating storage", async () => {
    listHistory.mockRejectedValueOnce(new Error("IndexedDB unavailable"))
    listHistory.mockResolvedValue([
      { id: "r1", question: "Recovered run", createdAt: 1 },
    ])
    renderSidebar()
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }))
    expect(await screen.findByText("Recovered run")).toBeTruthy()
    await waitFor(() => expect(screen.queryByTestId("history-load-error")).toBeNull())
    expect(listHistory).toHaveBeenCalledTimes(2)
    expect(deleteHistory).not.toHaveBeenCalled()
    expect(importJSON).not.toHaveBeenCalled()
  })

  it("ignores an older history-change failure after Retry succeeds", async () => {
    let rejectOlderRead!: (reason: Error) => void
    let resolveRetryRead!: (items: { id: string; question: string }[]) => void

    listHistory
      .mockRejectedValueOnce(new Error("Initial read failed"))
      .mockImplementationOnce(() => new Promise((_resolve, reject) => {
        rejectOlderRead = reject
      }))
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveRetryRead = resolve
      }))

    renderSidebar()
    expect(await screen.findByTestId("history-load-error")).toBeTruthy()

    // Start an event-driven read, then supersede it with the user's Retry.
    window.dispatchEvent(new Event("assembly:history-change"))
    fireEvent.click(screen.getByRole("button", { name: "Retry" }))

    resolveRetryRead([{ id: "r2", question: "Recovered after retry" }])
    expect(await screen.findByText("Recovered after retry")).toBeTruthy()
    await waitFor(() => expect(screen.queryByTestId("history-load-error")).toBeNull())

    // The older request fails after Retry has already recovered successfully.
    rejectOlderRead(new Error("Stale history-change read failed"))
    await waitFor(() => expect(screen.getByText("Recovered after retry")).toBeTruthy())
    expect(screen.queryByTestId("history-load-error")).toBeNull()
    expect(listHistory).toHaveBeenCalledTimes(3)
  })
})
