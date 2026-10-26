/**
 * Typed semantic status model for chat status messages.
 *
 * Replaces fragile string-based classification (every message that did not
 * match a hard-coded progress string was rendered as an error) with an
 * explicit semantic type carried alongside the display text.
 *
 * The semantic type determines both presentation and ARIA live-region
 * semantics. The display text is kept separate from the type so that the
 * renderer can never infer severity from wording.
 */

export type ChatStatusType = "info" | "progress" | "success" | "warning" | "error"

export interface ChatStatus {
  /** Semantic type. Determines presentation and live-region semantics. */
  type: ChatStatusType
  /** Human-readable display text, kept separate from the semantic type. */
  text: string
}

/** Presentation style for each semantic type, following the design system. */
export function chatStatusClass(type: ChatStatusType): string {
  switch (type) {
    case "info":
      return "border-info/30 bg-info-subtle text-info"
    case "progress":
      return "border-brand/30 bg-brand/10 text-brand"
    case "success":
      return "border-success/30 bg-success-subtle text-success"
    case "warning":
      return "border-warning/30 bg-warning-subtle text-warning"
    case "error":
      return "border-danger/40 bg-danger-subtle text-danger"
  }
  // Safe fallback: never treat an unrecognized status as an error.
  return "border-border bg-muted/40 text-muted-foreground"
}

/** ARIA role for each semantic type. Only genuine errors are alerts. */
export function chatStatusRole(type: ChatStatusType): "alert" | "status" {
  switch (type) {
    case "error":
      return "alert"
    default:
      return "status"
  }
}

/** ARIA live-region politeness for each semantic type. */
export function chatStatusAriaLive(type: ChatStatusType): "assertive" | "polite" {
  switch (type) {
    case "error":
      return "assertive"
    default:
      return "polite"
  }
}

/** Safe fallback for missing or invalid status values: neutral info, never error. */
export function safeChatStatus(text: string): ChatStatus {
  return { type: "info", text }
}

/** Build a typed status, defaulting an unknown/missing type to info (safe default). */
export function makeChatStatus(text: string, type?: ChatStatusType): ChatStatus {
  return { type: type ?? "info", text }
}
