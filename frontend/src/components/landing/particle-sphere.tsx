"use client"

import { useEffect, useRef, type RefObject } from "react"
import type { MotionField } from "./use-motion-input"

type Particle = {
  // Rest position on the unit sphere.
  hx: number
  hy: number
  hz: number
  // Live position and velocity in the same object space.
  x: number
  y: number
  z: number
  vx: number
  vy: number
  vz: number
  size: number
  seed: number
  // Last projected point, used for a short motion streak.
  sx: number
  sy: number
  hasScreen: boolean
  // Current projected point.
  screenX: number
  screenY: number
  screenZ: number
  screenSize: number
}

type Palette = {
  brand: string
  tail: string
  glow: string
}

function fibonacciSphere(count: number): Particle[] {
  const points: Particle[] = []
  const golden = Math.PI * (3 - Math.sqrt(5))
  for (let index = 0; index < count; index += 1) {
    const y = 1 - (index / Math.max(1, count - 1)) * 2
    const radius = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = golden * index
    // Thin out the very centre so the sphere reads as a surface, not a blob.
    const jitter = 0.94 + ((index * 37) % 13) / 100
    const hx = Math.cos(theta) * radius * jitter
    const hy = y
    const hz = Math.sin(theta) * radius * jitter
    points.push({
      hx,
      hy,
      hz,
      x: hx,
      y: hy,
      z: hz,
      vx: 0,
      vy: 0,
      vz: 0,
      size: 0.7 + ((index * 17) % 23) / 22,
      seed: ((index * 53) % 100) / 16,
      sx: 0,
      sy: 0,
      hasScreen: false,
      screenX: 0,
      screenY: 0,
      screenZ: 0,
      screenSize: 0,
    })
  }
  return points
}

function hexToRgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "").trim()
  const full = value.length === 3 ? value.split("").map((part) => part + part).join("") : value
  const parsed = Number.parseInt(full, 16)
  if (Number.isNaN(parsed)) return [245, 147, 39]
  return [(parsed >> 16) & 255, (parsed >> 8) & 255, parsed & 255]
}

function mix(a: [number, number, number], b: [number, number, number], t: number) {
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * t)} ${Math.round(a[1] + (b[1] - a[1]) * t)} ${Math.round(
    a[2] + (b[2] - a[2]) * t,
  )})`
}

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value))
}

export function ParticleSphere({
  field,
  className = "",
}: {
  field: RefObject<MotionField>
  className?: string
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext("2d")
    if (!context) return

    const motionQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)")
    let reduced = motionQuery?.matches ?? false
    const onMotionPreference = () => {
      reduced = motionQuery?.matches ?? false
    }
    motionQuery?.addEventListener?.("change", onMotionPreference)

    const count = window.innerWidth < 720 ? 950 : 2100
    const particles = fibonacciSphere(count)
    let width = 0
    let height = 0
    let dpr = 1
    let palette: Palette = { brand: "#f59327", tail: "#8d877a", glow: "#f59327" }

    const readPalette = () => {
      const styles = getComputedStyle(canvas)
      palette = {
        brand: styles.getPropertyValue("--brand").trim() || "#f59327",
        tail: styles.getPropertyValue("--muted-foreground").trim() || "#8d877a",
        glow: styles.getPropertyValue("--brand").trim() || "#f59327",
      }
    }

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = Math.max(1, rect.width)
      height = Math.max(1, rect.height)
      dpr = Math.min(2, window.devicePixelRatio || 1)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      readPalette()
      for (const particle of particles) particle.hasScreen = false
    }

    resize()
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvas)

    const themeObserver = new MutationObserver(readPalette)
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })

    const brandRgb = () => hexToRgb(palette.brand)
    const tailRgb = () => hexToRgb(palette.tail)

    let raf = 0
    let yaw = 0.45
    let pitch = -0.16
    let spin = 0
    let cloudX = 0
    let cloudY = 0
    let scatter = 1
    let handX = 0
    let handY = 0
    let handVX = 0
    let handVY = 0
    let handInfluence = 0
    let handWasOn = false
    // A single radial impulse when the hand first appears: the ball visibly
    // puffs apart before the springs pull it back together.
    let burst = 0
    let visible = true
    let lastTime = performance.now()

    const visibilityObserver = new IntersectionObserver(
      (entries) => {
        const nextVisible = entries.some((entry) => entry.isIntersecting)
        if (nextVisible && !visible) {
          visible = true
          lastTime = performance.now()
          raf = window.requestAnimationFrame(render)
        } else {
          visible = nextVisible
        }
      },
      { threshold: 0.05 },
    )
    visibilityObserver.observe(canvas)

    const render = (time: number) => {
      if (!visible) return
      const dt = Math.min(0.033, Math.max(0.001, (time - lastTime) / 1000))
      lastTime = time

      const rect = canvas.getBoundingClientRect()
      if (rect.width !== width || rect.height !== height) resize()

      const motion = field.current
      const hand = motion.hand
      const handOn = motion.source === "camera" && hand.present

      // The hand carries the whole cloud; a soft cap keeps the ball inside
      // the HUD frame even when the hand reaches the edge of the camera.
      const targetCloudX = handOn ? Math.max(-0.55, Math.min(0.55, hand.x * 0.85)) : 0
      const targetCloudY = handOn ? Math.max(-0.5, Math.min(0.5, hand.y * 0.85)) : 0
      const cloudEase = 1 - Math.exp(-dt * (handOn ? 4.8 : 1.8))
      cloudX += (targetCloudX - cloudX) * cloudEase
      cloudY += (targetCloudY - cloudY) * cloudEase

      // Open hand → the cloud loosens and expands; fist → particles gather in.
      const targetScatter = 1 + (handOn ? hand.spread * 0.5 + hand.energy * 0.1 : 0)
      scatter += (targetScatter - scatter) * (1 - Math.exp(-dt * 4.2))

      if (handOn && !handWasOn) burst = 1
      handWasOn = handOn
      burst *= Math.exp(-dt * 2.6)

      const previousHandX = handX
      const previousHandY = handY
      const targetHandX = handOn ? hand.x * 1.5 : 0
      const targetHandY = handOn ? hand.y * 1.5 : 0
      const handEase = 1 - Math.exp(-dt * (handOn ? 22 : 7))
      handX += (targetHandX - handX) * handEase
      handY += (targetHandY - handY) * handEase
      handVX = Math.max(-7, Math.min(7, (handX - previousHandX) / Math.max(dt, 0.001)))
      handVY = Math.max(-7, Math.min(7, (handY - previousHandY) / Math.max(dt, 0.001)))
      handInfluence += ((handOn ? 1 : 0) - handInfluence) * (1 - Math.exp(-dt * 6))

      if (!reduced) spin += dt * (0.055 + (handOn ? hand.energy * 0.22 : 0))
      const pointerInfluence = motion.source === "pointer" ? 1 : 0
      const targetYaw = 0.45 + spin + (handOn ? hand.x * 0.36 : motion.x * 0.55 * pointerInfluence)
      const targetPitch =
        -0.16 +
        (handOn ? hand.y * 0.24 : motion.y * 0.34 * pointerInfluence) +
        (reduced ? 0 : Math.sin(time * 0.00022) * 0.05)
      const turnEase = 1 - Math.exp(-dt * 4)
      yaw += (targetYaw - yaw) * turnEase
      pitch += (targetPitch - pitch) * turnEase

      const breathing = reduced ? 1 : 1 + Math.sin(time * 0.0005) * 0.012
      const depthScale = 1 + (handOn ? hand.depth * 0.12 : 0)

      // Integration: fixed substeps keep the springs stable on slow frames.
      const steps = dt > 0.022 ? 2 : 1
      const h = dt / steps
      // An open hand loosens the springs so particles can float apart.
      const loosen = handOn ? hand.spread * handInfluence : 0
      const spring = 20 - loosen * 5
      const damping = Math.exp(-h * 3.7)
      const handWorldX = handX
      const handWorldY = handY
      // The hand sits between the camera and the sphere: z is negative on the
      // near face, so the force carves a visible cavity in the front surface.
      const handWorldZ = -0.8 - (handOn ? hand.depth * 0.08 : 0)
      const handRadius = 0.3 + (handOn ? hand.spread * 0.08 + hand.energy * 0.04 : 0)
      const handRadius2 = handRadius * handRadius
      const push = handOn ? (4.5 + hand.energy * 14) * handInfluence : 0
      const pull = handOn ? hand.grab * 14 * handInfluence : 0
      const turbulence = reduced ? 0 : handOn ? hand.energy * 0.9 : motion.energy * 0.3
      // The whole cloud is also dragged along the hand's path, so a sweep
      // carries every particle with it, not just the ones near the palm.
      const windX = handOn ? handVX * handInfluence * (0.3 + loosen * 0.4) : 0
      const windY = handOn ? handVY * handInfluence * (0.3 + loosen * 0.4) : 0
      const outward = handOn
        ? (burst * 5 * (0.6 + hand.spread) + hand.spread * 1.2) * handInfluence
        : 0

      for (let step = 0; step < steps; step += 1) {
        for (const particle of particles) {
          const homeX = particle.hx * scatter + cloudX
          const homeY = particle.hy * scatter + cloudY
          const homeZ = particle.hz * scatter
          let ax = (homeX - particle.x) * spring
          let ay = (homeY - particle.y) * spring
          let az = (homeZ - particle.z) * spring

          if (Math.abs(windX) + Math.abs(windY) > 0.001) {
            ax += windX
            ay += windY
          }

          if (outward > 0.01) {
            const length = Math.sqrt(particle.x * particle.x + particle.y * particle.y + particle.z * particle.z) + 0.001
            const radial = outward / length
            ax += particle.x * radial
            ay += particle.y * radial
            az += particle.z * radial
          }

          if (handInfluence > 0.01) {
            const dx = particle.x - handWorldX
            const dy = particle.y - handWorldY
            const dz = particle.z - handWorldZ
            const distance2 = dx * dx + dy * dy + dz * dz
            if (distance2 < handRadius2 * 9) {
              const influence = Math.exp(-distance2 / handRadius2)
              const distance = Math.sqrt(distance2) + 0.0001
              const force = (push - pull) * (influence / distance)
              ax += dx * force
              ay += dy * force
              az += dz * force
              // The wake is what visibly tears particles out of the sphere.
              ax += handVX * influence * 2.4 * handInfluence
              ay += handVY * influence * 2.4 * handInfluence
            }
          }

          if (turbulence > 0.001) {
            ax += Math.sin(particle.y * 2.7 + time * 0.0011 + particle.seed) * turbulence
            ay += Math.cos(particle.x * 2.4 - time * 0.0009 + particle.seed) * turbulence
          }

          particle.vx = (particle.vx + ax * h) * damping
          particle.vy = (particle.vy + ay * h) * damping
          particle.vz = (particle.vz + az * h) * damping
          particle.x += particle.vx * h
          particle.y += particle.vy * h
          particle.z += particle.vz * h

          // Keep the cloud in front of the virtual camera; without this a
          // strong wave can push particles through the projection plane.
          if (particle.z < -1.3) particle.z = -1.3
          else if (particle.z > 1.5) particle.z = 1.5
          if (particle.x < -2.2) particle.x = -2.2
          else if (particle.x > 2.2) particle.x = 2.2
          if (particle.y < -2.2) particle.y = -2.2
          else if (particle.y > 2.2) particle.y = 2.2
        }
      }

      // Keep the cloud readable even during a vigorous wave.
      for (const particle of particles) {
        const speed2 = particle.vx * particle.vx + particle.vy * particle.vy + particle.vz * particle.vz
        if (speed2 > 144) {
          const scale = Math.sqrt(144 / speed2)
          particle.vx *= scale
          particle.vy *= scale
          particle.vz *= scale
        }
      }

      // cloudX/cloudY already move the particles in object space; keeping the
      // projection centred avoids moving the cloud twice.
      const cx = width / 2
      const cy = height / 2
      const radius = Math.min(width, height) * 0.3
      const fov = 3.1
      const cosYaw = Math.cos(yaw)
      const sinYaw = Math.sin(yaw)
      const cosPitch = Math.cos(pitch)
      const sinPitch = Math.sin(pitch)
      const globalScale = breathing * depthScale

      context.clearRect(0, 0, width, height)

      for (const particle of particles) {
        const x1 = particle.x * cosYaw - particle.z * sinYaw
        const z1 = particle.x * sinYaw + particle.z * cosYaw
        const y1 = particle.y * cosPitch - z1 * sinPitch
        const z2 = particle.y * sinPitch + z1 * cosPitch
        const perspective = fov / (fov + z2 * 0.92)
        particle.screenX = cx + x1 * radius * perspective * globalScale
        particle.screenY = cy + y1 * radius * perspective * globalScale
        particle.screenZ = z2
        particle.screenSize = particle.size * perspective * globalScale
      }

      particles.sort((a, b) => b.screenZ - a.screenZ)

      const warm = brandRgb()
      const cool = tailRgb()
      context.lineCap = "round"

      for (const particle of particles) {
        const nearness = clamp01((1.25 - particle.screenZ) / 2.5)
        const alpha = 0.16 + nearness * 0.8
        const twinkle = 0.82 + Math.sin(time * 0.0013 + particle.seed) * 0.18
        const vertical = clamp01((particle.y + 1) / 2)
        const color = mix(warm, cool, 1 - vertical)
        const size = Math.max(0.55, particle.screenSize * 1.65)

        if (particle.hasScreen) {
          const sx = particle.screenX - particle.sx
          const sy = particle.screenY - particle.sy
          if (sx * sx + sy * sy > 3.5) {
            context.globalAlpha = alpha * 0.44 * twinkle
            context.strokeStyle = color
            context.lineWidth = Math.max(0.5, size * 0.6)
            context.beginPath()
            context.moveTo(particle.sx, particle.sy)
            context.lineTo(particle.screenX, particle.screenY)
            context.stroke()
          }
        }

        context.globalAlpha = alpha * twinkle
        context.fillStyle = color
        context.fillRect(
          particle.screenX - size / 2,
          particle.screenY - size / 2,
          size,
          size,
        )

        particle.sx = particle.screenX
        particle.sy = particle.screenY
        particle.hasScreen = true
      }
      context.globalAlpha = 1

      // Hand feedback: a hairline field ring around the tracked hand.
      if (handOn && hand.confidence > 0.1) {
        const glowX = width / 2 + hand.x * width * 0.37
        const glowY = height / 2 + hand.y * height * 0.37
        const ringRadius = Math.min(width, height) * (0.055 + hand.spread * 0.1)
        context.globalAlpha = 0.35 + hand.confidence * 0.35
        context.strokeStyle = palette.brand
        context.lineWidth = 0.8
        context.setLineDash(hand.grab > 0.5 ? [] : [2, 6])
        context.beginPath()
        context.arc(glowX, glowY, ringRadius, 0, Math.PI * 2)
        context.stroke()
        context.setLineDash([])

        context.beginPath()
        context.moveTo(glowX - ringRadius - 4, glowY)
        context.lineTo(glowX - ringRadius + 4, glowY)
        context.moveTo(glowX + ringRadius - 4, glowY)
        context.lineTo(glowX + ringRadius + 4, glowY)
        context.moveTo(glowX, glowY - ringRadius - 4)
        context.lineTo(glowX, glowY - ringRadius + 4)
        context.moveTo(glowX, glowY + ringRadius - 4)
        context.lineTo(glowX, glowY + ringRadius + 4)
        context.stroke()
      }
      context.globalAlpha = 1

      // A faint orbital arc anchors the cloud to the HUD frame.
      context.beginPath()
      context.ellipse(cx, cy, radius * 1.075, radius * 0.3, -0.2, 0, Math.PI * 2)
      context.strokeStyle = palette.glow
      context.globalAlpha = 0.14
      context.lineWidth = 0.8
      context.setLineDash([3, 7])
      context.stroke()
      context.setLineDash([])
      context.globalAlpha = 1

      raf = window.requestAnimationFrame(render)
    }

    raf = window.requestAnimationFrame(render)

    return () => {
      window.cancelAnimationFrame(raf)
      resizeObserver.disconnect()
      themeObserver.disconnect()
      visibilityObserver.disconnect()
      motionQuery?.removeEventListener?.("change", onMotionPreference)
    }
  }, [field])

  return <canvas ref={canvasRef} className={`asm-orb-canvas ${className}`} aria-hidden="true" />
}
