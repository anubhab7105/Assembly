import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

const globalStyles = readFileSync(new URL("./globals.css", import.meta.url), "utf8")
const chatPage = readFileSync(new URL("./chat/page.tsx", import.meta.url), "utf8")
const reducedMotionBlock = globalStyles.match(
  /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?)\n\}\n\n\/\* Ensure Next\.js dev overlay/,
)?.[1]

describe("global reduced-motion support", () => {
  it("disables animations, transitions, and smooth scrolling", () => {
    expect(reducedMotionBlock).toBeDefined()
    expect(reducedMotionBlock).toContain("animation: none !important")
    expect(reducedMotionBlock).toContain("transition: none !important")
    expect(reducedMotionBlock).toContain("scroll-behavior: auto !important")
  })

  it("keeps indeterminate progress static while status text remains available", () => {
    expect(reducedMotionBlock).toContain(".animate-progress-indeterminate")
    expect(reducedMotionBlock).toContain("transform: none !important")
    expect(chatPage).toContain('makeChatStatus("Checking capacity…", "progress")')
  })
})
