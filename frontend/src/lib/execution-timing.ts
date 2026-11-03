export interface ExecutionTiming {
  label: string
  seconds: number | null
}

const ACTIVE_STATES = new Set([
  "starting",
  "running",
  "created",
  "capacity_check",
  "planning",
  "team_ready",
  "solving",
  "evaluating",
  "debating",
  "synthesizing",
])

const TERMINAL_STATES = new Set([
  "completed",
  "cancelled",
  "failed",
  "failed_partial",
])

function validSeconds(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null
}

/**
 * Select a truthful timing label/value pair for an execution lifecycle state.
 * Live remaining-time estimates are never reused for terminal or unknown runs.
 */
export function getExecutionTiming(
  status: string,
  remainingSeconds: number | null,
  elapsedSeconds: number | null,
): ExecutionTiming {
  if (TERMINAL_STATES.has(status)) {
    return {
      label: status === "completed" ? "Elapsed" : "Duration",
      seconds: validSeconds(elapsedSeconds),
    }
  }

  if (ACTIVE_STATES.has(status)) {
    const remaining = validSeconds(remainingSeconds)
    return remaining === null
      ? { label: "Time Unavailable", seconds: null }
      : { label: "Time Remaining", seconds: remaining }
  }

  // Idle, legacy and unrecognized statuses do not establish a live deadline.
  return { label: "Time Unavailable", seconds: null }
}
