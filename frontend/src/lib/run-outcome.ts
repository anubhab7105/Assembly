/**
 * Run-outcome guard: a failed or incomplete run must never be presented as
 * a normal execution (empty team that looks like it is still forming).
 *
 * A run is presentable only when the stream ended with status "completed"
 * AND a non-empty final answer arrived via execution.completed. Anything
 * else is a failure state: history is preserved with the failed status,
 * but the UI stays on an explicit failure message and never navigates to
 * the active-run screen.
 */

export type PresentableRunStatus = "completed" | "failed" | "cancelled" | "unknown"

export interface RunOutcome {
  status: string
  finalAnswer: string
}

export function isPresentableRun({ status, finalAnswer }: RunOutcome): boolean {
  return status === "completed" && finalAnswer.trim().length > 0
}

/** Actionable failure message with safe diagnostics only (no keys/bodies). */
export function failureMessage(args: {
  status: string
  stage?: string
  errorCode?: string
}): string {
  const stage = args.stage ? ` during ${args.stage}` : ""
  const code = args.errorCode ? ` (${args.errorCode})` : ""
  if (args.status === "cancelled") {
    return "Run cancelled before completing. Start a new run when ready."
  }
  return (
    `Run ${args.status}${stage}${code}. ` +
    "Check your provider keys and quota, then try again. " +
    "The failed run was saved to history without an answer."
  )
}
