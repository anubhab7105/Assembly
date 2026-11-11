"use client"

import { useEffect, useRef, type RefObject } from "react"

type StarTone = "core" | "violet" | "mint" | "white" | "blue" | "deep"
type SpeckTone = "violet" | "mint" | "white"

type Star = {
  /** Position on the disk, in polar coordinates. */
  angle: number
  radius: number
  /** Vertical thickness of the disk. */
  height: number
  size: number
  tone: StarTone
  phase: number
  brightness: number
  flare: boolean
}

type Speck = {
  /** Normalised position across the canvas. */
  x: number
  y: number
  size: number
  alpha: number
  phase: number
  tone: SpeckTone
}

/**
 * Bright stars on the dark hero, deep ink stars on the light hero. The light
 * palette keeps the same hues but pushes them dark enough to read on a pale
 * background.
 */
const STAR_COLORS: Record<"dark" | "light", Record<StarTone, string>> = {
  dark: {
    core: "#ffe6bd",
    violet: "#c3a6ff",
    mint: "#9fe4cf",
    white: "#e8f1ff",
    blue: "#c2d8ff",
    deep: "#94b9ff",
  },
  light: {
    core: "#b26a00",
    violet: "#6d4aff",
    mint: "#0b8f70",
    white: "#173a7a",
    blue: "#2a5fb8",
    deep: "#4f7fd6",
  },
}

const SPECK_COLORS: Record<"dark" | "light", Record<SpeckTone, string>> = {
  dark: { violet: "#b8a6ff", mint: "#9fe4cf", white: "#dbe8ff" },
  light: { violet: "#7c5cff", mint: "#0f9b7a", white: "#6f86ad" },
}

const ARMS = 2
const TWIST = 3.8
/** Inclination of the disk: 0 is face-on, PI / 2 is edge-on. */
const TILT = 0.42
const Z_ROT = -0.16
/** Radians per second. A full turn takes a little under two minutes. */
const SPIN = 0.058

function mulberry32(seed: number): () => number {
  let state = seed
  return () => {
    state |= 0
    state = (state + 0x6d2b79f5) | 0
    let value = Math.imul(state ^ (state >>> 15), 1 | state)
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
}

function gaussian(rand: () => number): number {
  const u = Math.max(1e-6, rand())
  const v = rand()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(Math.PI * 2 * v)
}

/**
 * Stars live in a thin disk. Most of them follow one of four logarithmic arms;
 * the rest fill the disk and the halo so the arms never look like hard lines.
 */
function buildStars(count: number): Star[] {
  const rand = mulberry32(0x5eed2026)
  const stars: Star[] = []

  for (let index = 0; index < count; index += 1) {
    const arm = index % ARMS
    const radial = Math.pow(rand(), 0.85)
    const inArm = rand() > 0.04
    const spread = (0.06 + (1 - radial) * 0.2) * (inArm ? 1 : 4)
    const angle = inArm
      ? arm * ((Math.PI * 2) / ARMS) + radial * TWIST + gaussian(rand) * spread
      : rand() * Math.PI * 2
    const radius = Math.min(
      1.08,
      Math.max(0.035, 0.05 + radial * 1.02 + gaussian(rand) * 0.03),
    )
    const bulge = Math.exp(-radial * 4.6)
    const height = gaussian(rand) * (0.012 + bulge * 0.075)
    const roll = rand()

    let tone: StarTone = "blue"
    if (radial < 0.15 && roll < 0.62) tone = "core"
    else if (roll < 0.06) tone = "violet"
    else if (roll < 0.11) tone = "mint"
    else if (roll < 0.48) tone = "white"
    else if (roll < 0.78) tone = "blue"
    else tone = "deep"

    const sizeRoll = rand()
    stars.push({
      angle,
      radius,
      height,
      size: 0.5 + sizeRoll * sizeRoll * 2,
      tone,
      phase: rand() * Math.PI * 2,
      brightness: inArm ? 0.5 + rand() * 0.5 : 0.18 + rand() * 0.22,
      flare: index % 137 === 0,
    })
  }

  return stars
}

function buildSpecks(count: number): Speck[] {
  const rand = mulberry32(0x51a7f13)
  const specks: Speck[] = []

  for (let index = 0; index < count; index += 1) {
    const roll = rand()
    specks.push({
      x: rand(),
      y: rand(),
      size: 0.5 + rand() * 1.3,
      alpha: 0.18 + rand() * 0.55,
      phase: rand() * Math.PI * 2,
      tone: roll < 0.1 ? "violet" : roll < 0.18 ? "mint" : "white",
    })
  }

  return specks
}

export function GalaxyField({
  heroRef,
  className = "",
}: {
  heroRef?: RefObject<HTMLElement | null>
  className?: string
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext("2d", { alpha: true })
    if (!context) return

    const motionQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)")
    let reduced = motionQuery?.matches ?? false
    const compact = window.innerWidth < 720
    const stars = buildStars(compact ? 1900 : 3600)
    const specks = buildSpecks(compact ? 70 : 120)

    let width = 1
    let height = 1
    let dpr = 1
    let raf = 0
    let running = false
    let visible = true
    let elapsed = 0
    let last = performance.now()
    let dark = document.documentElement.classList.contains("dark")

    const draw = (time: number) => {
      const cx = width * 0.52
      const cy = height * 0.5
      const radius = Math.min(width, height) * 0.45
      const cosTilt = Math.cos(TILT)
      const sinTilt = Math.sin(TILT)
      const cosZ = Math.cos(Z_ROT)
      const sinZ = Math.sin(Z_ROT)
      const fov = 2.7
      const starColors = dark ? STAR_COLORS.dark : STAR_COLORS.light
      const speckColors = dark ? SPECK_COLORS.dark : SPECK_COLORS.light

      context.clearRect(0, 0, width, height)

      // Sparse background stars, independent of the disk.
      for (const speck of specks) {
        const twinkle = 0.68 + Math.sin(time * 0.9 + speck.phase) * 0.32
        context.globalAlpha = speck.alpha * twinkle * (dark ? 1 : 0.55)
        context.fillStyle = speckColors[speck.tone]
        context.fillRect(speck.x * width, speck.y * height, speck.size, speck.size)
      }

      // A wide, soft nebula so the disk has something to sit inside. The
      // ellipse is squashed to match the disk's inclination.
      context.save()
      context.translate(cx, cy)
      context.scale(1, 0.44)
      const halo = context.createRadialGradient(0, 0, radius * 0.04, 0, 0, radius * 1.02)
      if (dark) {
        halo.addColorStop(0, "rgba(255, 233, 196, 0.4)")
        halo.addColorStop(0.16, "rgba(172, 160, 255, 0.24)")
        halo.addColorStop(0.5, "rgba(82, 105, 230, 0.13)")
        halo.addColorStop(1, "rgba(10, 14, 40, 0)")
      } else {
        halo.addColorStop(0, "rgba(255, 214, 160, 0.3)")
        halo.addColorStop(0.16, "rgba(124, 92, 255, 0.12)")
        halo.addColorStop(0.5, "rgba(37, 99, 235, 0.07)")
        halo.addColorStop(1, "rgba(238, 243, 252, 0)")
      }
      context.globalAlpha = 1
      context.fillStyle = halo
      context.beginPath()
      context.arc(0, 0, radius * 1.02, 0, Math.PI * 2)
      context.fill()
      context.restore()

      // Warm bulge.
      const core = context.createRadialGradient(cx, cy, 0, cx, cy, radius * 0.17)
      if (dark) {
        core.addColorStop(0, "rgba(255, 250, 236, 1)")
        core.addColorStop(0.22, "rgba(255, 226, 175, 0.72)")
        core.addColorStop(0.58, "rgba(196, 170, 255, 0.2)")
        core.addColorStop(1, "rgba(120, 140, 255, 0)")
      } else {
        core.addColorStop(0, "rgba(255, 240, 214, 0.95)")
        core.addColorStop(0.22, "rgba(236, 168, 74, 0.55)")
        core.addColorStop(0.58, "rgba(124, 92, 255, 0.14)")
        core.addColorStop(1, "rgba(37, 99, 235, 0)")
      }
      context.fillStyle = core
      context.beginPath()
      context.arc(cx, cy, radius * 0.17, 0, Math.PI * 2)
      context.fill()

      for (const star of stars) {
        const angle = star.angle + time * SPIN
        const x = Math.cos(angle) * star.radius
        const z = Math.sin(angle) * star.radius
        const y = star.height

        // Tilt the disk toward the viewer, then rotate the projected ellipse.
        const y1 = y * cosTilt - z * sinTilt
        const z1 = y * sinTilt + z * cosTilt
        const x2 = x * cosZ - y1 * sinZ
        const y2 = x * sinZ + y1 * cosZ
        const perspective = fov / (fov + z1 * 0.55)
        const sx = cx + x2 * radius * perspective
        const sy = cy + y2 * radius * perspective

        if (sx < -24 || sx > width + 24 || sy < -24 || sy > height + 24) continue

        const depth = Math.min(1, Math.max(0, (1 - z1) * 0.5))
        const twinkle = 0.78 + Math.sin(time * 1.25 + star.phase) * 0.22
        const alphaBase = dark ? 0.34 : 0.55
        const alphaDepth = dark ? 1 : 0.65
        const alpha = star.brightness * (alphaBase + depth * alphaDepth) * twinkle
        const size = Math.max(0.5, star.size * (0.8 + perspective * 0.45))

        context.globalAlpha = Math.min(1, alpha)
        context.fillStyle = starColors[star.tone]
        context.fillRect(sx - size / 2, sy - size / 2, size, size)

        if (size > 1.45) {
          const glow = size * 2.6
          context.globalAlpha = dark
            ? Math.min(0.32, alpha * 0.2)
            : Math.min(0.12, alpha * 0.08)
          context.fillRect(sx - glow / 2, sy - glow / 2, glow, glow)
        }

        if (star.flare) {
          const flare = size * 5
          context.globalAlpha = Math.min(dark ? 0.55 : 0.4, alpha * 0.55)
          context.strokeStyle = starColors[star.tone]
          context.lineWidth = 0.7
          context.beginPath()
          context.moveTo(sx - flare, sy)
          context.lineTo(sx + flare, sy)
          context.moveTo(sx, sy - flare)
          context.lineTo(sx, sy + flare)
          context.stroke()
        }
      }

      // The nucleus itself, on top of the disk.
      context.globalAlpha = 0.92
      context.fillStyle = dark ? "#fff6df" : "#b26a00"
      context.beginPath()
      context.arc(cx, cy, Math.max(1.6, radius * 0.014), 0, Math.PI * 2)
      context.fill()
      context.globalAlpha = 1
    }

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = Math.max(1, rect.width)
      height = Math.max(1, rect.height)
      dpr = Math.min(2, window.devicePixelRatio || 1)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      if (reduced) draw(elapsed)
    }

    const frame = (now: number) => {
      if (!running) return
      const dt = Math.min(0.05, Math.max(0, (now - last) / 1000))
      last = now
      if (!reduced) elapsed += dt
      draw(elapsed)
      if (reduced) {
        running = false
        return
      }
      raf = window.requestAnimationFrame(frame)
    }

    const start = () => {
      if (running || !visible || document.hidden) return
      running = true
      last = performance.now()
      raf = window.requestAnimationFrame(frame)
    }

    const stop = () => {
      running = false
      window.cancelAnimationFrame(raf)
    }

    const onMotionPreference = () => {
      reduced = motionQuery?.matches ?? false
      stop()
      if (reduced) draw(elapsed)
      else start()
    }

    const onVisibility = () => {
      if (document.hidden) stop()
      else start()
    }

    const onThemeChange = () => {
      const next = document.documentElement.classList.contains("dark")
      if (next === dark) return
      dark = next
      if (reduced) draw(elapsed)
    }

    const themeObserver = new MutationObserver(onThemeChange)
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
    window.addEventListener("assembly:theme-change", onThemeChange)

    resize()

    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvas)

    const intersectionObserver = new IntersectionObserver(
      (entries) => {
        visible = entries[0]?.isIntersecting ?? true
        if (visible) start()
        else stop()
      },
      { threshold: 0.02 },
    )
    intersectionObserver.observe(heroRef?.current ?? canvas)

    motionQuery?.addEventListener?.("change", onMotionPreference)
    document.addEventListener("visibilitychange", onVisibility)

    start()

    return () => {
      stop()
      resizeObserver.disconnect()
      intersectionObserver.disconnect()
      themeObserver.disconnect()
      motionQuery?.removeEventListener?.("change", onMotionPreference)
      document.removeEventListener("visibilitychange", onVisibility)
      window.removeEventListener("assembly:theme-change", onThemeChange)
    }
  }, [heroRef])

  return (
    <canvas
      ref={canvasRef}
      className={`cin-galaxy-canvas ${className}`.trim()}
      aria-hidden="true"
    />
  )
}
