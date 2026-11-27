import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

const globalStyles = readFileSync(new URL("./globals.css", import.meta.url), "utf8")
const chatPage = readFileSync(new URL("./chat/page.tsx", import.meta.url), "utf8")
const executionPage = readFileSync(new URL("./executions/page.tsx", import.meta.url), "utf8")
const brandOrbMark = readFileSync(new URL("../components/brand-orb-mark.tsx", import.meta.url), "utf8")
const textIntroScene = readFileSync(new URL("../components/text-intro-scene.tsx", import.meta.url), "utf8")
const heroExperience = readFileSync(new URL("../components/assembly-hero-experience.tsx", import.meta.url), "utf8")
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
    expect(executionPage).toContain("STAGES[Math.min(stageIndex, STAGES.length - 1)]")
  })

  it("pauses scripted decorative motion and automatic tab rotation", () => {
    expect(brandOrbMark).toContain('window.matchMedia("(prefers-reduced-motion: reduce)")')
    expect(textIntroScene).toContain("if (motionPreference.matches) completeWithoutMotion()")
    expect(textIntroScene).toContain("{!prefersReducedMotion && (")
    expect(heroExperience).toContain("if (motionPreference.matches)")
  })
})
