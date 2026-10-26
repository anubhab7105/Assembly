"use client"

import React from "react"
import {
  chatStatusAriaLive,
  chatStatusClass,
  chatStatusRole,
  type ChatStatus,
} from "@/lib/chat-status"

/**
 * Presentational chat status message.
 *
 * Renders a single live region whose role/politeness and styling are driven
 * by the semantic status type, never by the display text.
 *
 * - error   -> role="alert", aria-live="assertive" (genuine failures only)
 * - success/info/progress/warning -> role="status", aria-live="polite"
 *
 * A single status element is reused (text/type replaced in place), so
 * assistive technologies are notified of changes without nested live regions
 * or duplicated announcements.
 */
export function ChatStatusMessage({ status }: { status: ChatStatus }) {
  return (
    <p
      id="question-status"
      role={chatStatusRole(status.type)}
      aria-live={chatStatusAriaLive(status.type)}
      className={`rounded-lg border px-3 py-2 text-xs font-medium ${chatStatusClass(status.type)}`}
    >
      {status.text}
    </p>
  )
}
