import { describe, expect, it } from "vitest"
import { getExecutionTiming } from "./execution-timing"

describe("getExecutionTiming", () => {
  it("shows a genuine remaining estimate for active executions", () => {
    expect(getExecutionTiming("solving", 125, 40)).toEqual({
      label: "Time Remaining",
      seconds: 125,
    })
  })

  it("does not label an active execution as remaining when its estimate is missing", () => {
    expect(getExecutionTiming("planning", null, null)).toEqual({
      label: "Time Unavailable",
      seconds: null,
    })
  })

  it("uses elapsed time for completed executions even when a stale live timer exists", () => {
    expect(getExecutionTiming("completed", 10, 42.4)).toEqual({
      label: "Elapsed",
      seconds: 42.4,
    })
  })

  it.each(["cancelled", "failed", "failed_partial"])(
    "uses a duration label for %s executions",
    (status) => {
      expect(getExecutionTiming(status, 30, 18)).toEqual({
        label: "Duration",
        seconds: 18,
      })
    },
  )

  it("shows unavailable for unknown, idle and missing terminal timing data", () => {
    expect(getExecutionTiming("unknown", 90, null)).toEqual({
      label: "Time Unavailable",
      seconds: null,
    })
    expect(getExecutionTiming("idle", 90, null)).toEqual({
      label: "Time Unavailable",
      seconds: null,
    })
    expect(getExecutionTiming("completed", 90, null)).toEqual({
      label: "Elapsed",
      seconds: null,
    })
    expect(getExecutionTiming("failed", 90, Number.NaN)).toEqual({
      label: "Duration",
      seconds: null,
    })
  })
})
