import { describe, it, expect, vi } from "vitest"
import {
  importHistoryFile,
  MAX_IMPORT_FILE_SIZE,
} from "./history-import"

describe("History import file size validation", () => {
  it("allows a 4 MiB file", async () => {
    const file = {
      size: 4 * 1024 * 1024,
      text: vi.fn().mockResolvedValue("{}"),
    }

    const importJSON = vi.fn().mockResolvedValue(undefined)

    await importHistoryFile(file, importJSON)

    expect(file.text).toHaveBeenCalledOnce()
    expect(importJSON).toHaveBeenCalledWith("{}")
  })

  it("allows a file exactly 5 MiB", async () => {
    const file = {
      size: MAX_IMPORT_FILE_SIZE,
      text: vi.fn().mockResolvedValue("{}"),
    }

    const importJSON = vi.fn().mockResolvedValue(undefined)

    await importHistoryFile(file, importJSON)

    expect(file.text).toHaveBeenCalledOnce()
    expect(importJSON).toHaveBeenCalledWith("{}")
  })

  it("rejects a file larger than 5 MiB before reading it", async () => {
    const file = {
      size: 6 * 1024 * 1024,
      text: vi.fn().mockResolvedValue("{}"),
    }

    const importJSON = vi.fn().mockResolvedValue(undefined)

    await expect(
      importHistoryFile(file, importJSON)
    ).rejects.toThrow(
      "This file is too large to import."
    )

    expect(file.text).not.toHaveBeenCalled()
    expect(importJSON).not.toHaveBeenCalled()
  })
})