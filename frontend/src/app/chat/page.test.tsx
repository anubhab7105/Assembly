import React from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import Home from "./page"

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("@/lib/key-vault", () => ({
  globalVault: {
    allKeys: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock("@/lib/api-client", () => ({
  ApiClient: {
    catalog: vi.fn().mockResolvedValue({ providers: [], families: [] }),
    preflight: vi.fn(),
    startRunStream: vi.fn(),
  },
}))

vi.mock("@/lib/storage", () => ({
  storage: {
    getSetting: vi.fn().mockResolvedValue(JSON.stringify({ version: 1 })),
    setSetting: vi.fn().mockResolvedValue(undefined),
    getUsage: vi.fn().mockResolvedValue([]),
    setUsage: vi.fn().mockResolvedValue(undefined),
    saveHistory: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock("@/components/model-picker", () => ({
  ModelPicker: () => null,
}))

vi.mock("@/components/privacy-dialog", () => ({
  PrivacyDialog: () => null,
}))

vi.mock("@/components/server-status-banner", () => ({
  ServerStatusBanner: () => null,
}))

const MiB = 1024 * 1024

function makePickedFile(name: string, size: number, content = "secret-file-body", type = "text/plain") {
  return {
    name,
    size,
    type,
    text: vi.fn().mockResolvedValue(content),
  }
}

function selectFiles(input: HTMLInputElement, files: Array<ReturnType<typeof makePickedFile>>) {
  Object.defineProperty(input, "files", {
    value: files,
    configurable: true,
  })
  fireEvent.change(input)
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("Chat page investigation attachment handling", () => {
  it("allows empty files, more than five attachments within 50 MiB, and keeps filename-only chips without content previews", async () => {
    render(<Home />)
    const input = screen.getByLabelText("Choose investigation attachments") as HTMLInputElement
    const attachButton = screen.getByRole("button", { name: "Attach files" })

    const canaryContent = "CONFIDENTIAL-CONTENT-MUST-NOT-RENDER"
    const batchOne = [
      makePickedFile("empty.txt", 0, ""),
      makePickedFile("part-1.txt", 8 * MiB, canaryContent),
      makePickedFile("part-2.txt", 8 * MiB, canaryContent),
    ]
    selectFiles(input, batchOne)

    await waitFor(() => {
      expect(screen.getByText(/3 files ready/i)).toBeTruthy()
    })

    // Attach button stays enabled after multiple files and accepts a second batch past 5 files.
    expect((attachButton as HTMLButtonElement).disabled).toBe(false)

    const batchTwo = [
      makePickedFile("part-3.txt", 8 * MiB, canaryContent),
      makePickedFile("part-4.txt", 8 * MiB, canaryContent),
      makePickedFile("part-5.txt", 8 * MiB, canaryContent),
      makePickedFile("part-6.txt", 8 * MiB, canaryContent),
    ]
    selectFiles(input, batchTwo)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Remove part-6.txt" })).toBeTruthy()
    })

    expect(screen.getByText("empty.txt")).toBeTruthy()
    expect(screen.getByText("part-6.txt")).toBeTruthy()
    expect((attachButton as HTMLButtonElement).textContent).toContain("7")
    expect((attachButton as HTMLButtonElement).disabled).toBe(false)
    expect(document.body.textContent).not.toContain(canaryContent)
  })

  it("rejects files over 10 MiB before reading and enforces the 50 MiB limit across batches and removals", async () => {
    render(<Home />)
    const input = screen.getByLabelText("Choose investigation attachments") as HTMLInputElement

    const oversized = makePickedFile("too-large.txt", 10.5 * MiB, "nope")
    selectFiles(input, [oversized])

    await waitFor(() => {
      expect(screen.getByText(/exceeds the 10 MiB per-file limit/i)).toBeTruthy()
    })
    expect(oversized.text).not.toHaveBeenCalled()

    // Upload 45 MiB in batch 1 (5 x 9 MiB).
    selectFiles(
      input,
      Array.from({ length: 5 }, (_, i) => makePickedFile(`nine-${i}.txt`, 9 * MiB, "ok")),
    )
    await waitFor(() => {
      expect(screen.getByText(/5 files ready/i)).toBeTruthy()
    })

    // A 6th 9 MiB file (total 54 MiB) in batch 2 must be rejected before reading.
    const sixthNine = makePickedFile("nine-5.txt", 9 * MiB, "overflow")
    selectFiles(input, [sixthNine])

    await waitFor(() => {
      expect(screen.getByText(/exceed the 50 MiB combined limit/i)).toBeTruthy()
    })
    expect(sixthNine.text).not.toHaveBeenCalled()
    expect(screen.queryByText("nine-5.txt")).toBeNull()

    // Removing one 9 MiB file frees capacity back down to 36 MiB so a 10 MiB file fits (46 MiB).
    fireEvent.click(screen.getByRole("button", { name: "Remove nine-0.txt" }))
    await waitFor(() => {
      expect(screen.queryByText("nine-0.txt")).toBeNull()
    })

    const tenMiB = makePickedFile("ten.txt", 10 * MiB, "fits now")
    selectFiles(input, [tenMiB])

    await waitFor(() => {
      expect(screen.getByText("ten.txt")).toBeTruthy()
    })
    expect(tenMiB.text).toHaveBeenCalledOnce()
  })
})

