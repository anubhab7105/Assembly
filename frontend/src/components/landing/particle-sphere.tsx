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

type ForceHand = {
  x: number
  y: number
  z: number
  radius2: number
  push: number
  pull: number
  vx: number
  vy: number
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

function clampSigned(value: number, limit: number) {
  return Math.min(limit, Math.max(-limit, value))
}

export function ParticleSphere({
  field,
  heroRef,
  className = "",
}: {
  field: RefObject<MotionField>
  heroRef?: RefObject<HTMLElement | null>
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

    // Screen position of the whole cloud. The canvas covers the viewport, so
    // this is also the point around which particles are projected.
    let cloudX = 0
    let cloudY = 0
    let previousCloudX = 0
    let previousCloudY = 0

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const firstSize = width === 0 || height === 0
      width = Math.max(1, rect.width)
      height = Math.max(1, rect.height)
      dpr = Math.min(2, window.devicePixelRatio || 1)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      readPalette()
      for (const particle of particles) particle.hasScreen = false
      if (firstSize) {
        cloudX = width / 2
        cloudY = height / 2
        previousCloudX = cloudX
        previousCloudY = cloudY
      } else {
        const edge = Math.min(width, height) * 0.06
        cloudX = Math.min(width - edge, Math.max(edge, cloudX))
        cloudY = Math.min(height - edge, Math.max(edge, cloudY))
      }
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
    let scatter = 1
    let handInfluence = 0
    let handWasOn = false
    let handWasTracked = false
    let wasTwoHands = false
    let previousOpenness = 0
    let burst = 0
    let previousPrimaryX = 0
    let previousPrimaryY = 0
    let previousSecondX = 0
    let previousSecondY = 0
    let visible = true
    let heroVisible = true
    let lastTime = performance.now()

    const drawRing = (
      x: number,
      y: number,
      radius: number,
      confidence: number,
      dashed: boolean,
    ) => {
      context.globalAlpha = 0.3 + confidence * 0.4
      context.strokeStyle = palette.brand
      context.lineWidth = 0.8
      context.setLineDash(dashed ? [2, 6] : [])
      context.beginPath()
      context.arc(x, y, radius, 0, Math.PI * 2)
      context.stroke()
      context.setLineDash([])

      context.beginPath()
      context.moveTo(x - radius - 4, y)
      context.lineTo(x - radius + 4, y)
      context.moveTo(x + radius - 4, y)
      context.lineTo(x + radius + 4, y)
      context.moveTo(x, y - radius - 4)
      context.lineTo(x, y - radius + 4)
      context.moveTo(x, y + radius - 4)
      context.lineTo(x, y + radius + 4)
      context.stroke()
    }

    const render = (time: number) => {
      if (!visible) return
      const dt = Math.min(0.033, Math.max(0.001, (time - lastTime) / 1000))
      lastTime = time

      const rect = canvas.getBoundingClientRect()
      if (rect.width !== width || rect.height !== height) resize()

      const motion = field.current
      const hand = motion.hand
      const handOn = motion.source === "camera" && hand.present
      const twoHands = handOn && hand.second !== null
      const pointerOn = motion.source === "pointer" && motion.pointerActive
      const sensorOn = motion.source === "sensor"

      const edge = Math.min(width, height) * 0.06
      let targetX = width / 2
      let targetY = height / 2
      if (handOn) {
        targetX = width / 2 + hand.x * (width / 2 - edge)
        targetY = height / 2 + hand.y * (height / 2 - edge)
      } else if (pointerOn) {
        targetX = edge + ((motion.targetX + 1) / 2) * (width - edge * 2)
        targetY = edge + ((motion.targetY + 1) / 2) * (height - edge * 2)
      } else if (sensorOn) {
        targetX = width / 2 + motion.targetX * width * 0.3
        targetY = height / 2 + motion.targetY * height * 0.3
      }
      targetX = Math.min(width - edge, Math.max(edge, targetX))
      targetY = Math.min(height - edge, Math.max(edge, targetY))

      // The cloud chases a screen-space point. Pointer movement is near-direct;
      // the hand is smoothed more so camera jitter does not shake the sphere.
      const follow = handOn ? 8 : pointerOn ? 11 : sensorOn ? 5 : 3.4
      const cloudEase = 1 - Math.exp(-dt * follow)
      previousCloudX = cloudX
      previousCloudY = cloudY
      cloudX += (targetX - cloudX) * cloudEase
      cloudY += (targetY - cloudY) * cloudEase
      const cloudVX = clampSigned((cloudX - previousCloudX) / Math.max(dt, 0.001), 2600)
      const cloudVY = clampSigned((cloudY - previousCloudY) / Math.max(dt, 0.001), 2600)

      // Two hands apart open the shell; bringing them together contracts it
      // below its resting size. A single open hand also loosens the cloud.
      const singleOpen = handOn ? clamp01((hand.spread - 0.22) / 0.7) : 0
      const openness = twoHands ? hand.span : handOn ? singleOpen : 0
      // Closed hands pull the shell below its resting size; spread hands open
      // it past the viewport edges.
      const targetScatter = handOn ? 0.58 + openness * 1.62 : 1
      scatter += (targetScatter - scatter) * (1 - Math.exp(-dt * (twoHands ? 5 : 3.6)))

      if (handOn && !handWasOn) burst = 1
      if (twoHands && !wasTwoHands) burst = Math.max(burst, 0.35)
      if (handOn) {
        const openDelta = Math.max(0, openness - previousOpenness)
        burst = Math.min(1.5, burst + openDelta * 2.1)
      }
      previousOpenness = handOn ? openness : 0
      handWasOn = handOn
      wasTwoHands = twoHands
      burst *= Math.exp(-dt * 2.3)

      handInfluence += ((handOn ? 1 : 0) - handInfluence) * (1 - Math.exp(-dt * 7))

      if (!reduced) spin += dt * (0.045 + (handOn ? hand.energy * 0.2 : 0))
      const targetYaw =
        0.45 +
        spin +
        (handOn ? hand.x * 0.28 : pointerOn ? motion.x * 0.42 : sensorOn ? motion.x * 0.24 : 0)
      const targetPitch =
        -0.16 +
        (handOn ? hand.y * 0.18 : pointerOn ? motion.y * 0.3 : sensorOn ? motion.y * 0.2 : 0) +
        (reduced ? 0 : Math.sin(time * 0.00022) * 0.05)
      const turnEase = 1 - Math.exp(-dt * 4)
      yaw += (targetYaw - yaw) * turnEase
      pitch += (targetPitch - pitch) * turnEase

      const breathing = reduced ? 1 : 1 + Math.sin(time * 0.0005) * 0.012
      const depthScale = 1 + (handOn ? hand.depth * 0.1 : 0)
      const globalScale = breathing * depthScale
      const radius = Math.min(width, height) * (width < 720 ? 0.32 : 0.23)
      const objectScale = Math.max(80, radius * globalScale)

      const primaryX = width / 2 + hand.first.x * (width / 2 - edge)
      const primaryY = height / 2 + hand.first.y * (height / 2 - edge)
      const secondX = hand.second ? width / 2 + hand.second.x * (width / 2 - edge) : 0
      const secondY = hand.second ? height / 2 + hand.second.y * (height / 2 - edge) : 0

      if (handOn) {
        if (!handWasTracked) {
          previousPrimaryX = primaryX
          previousPrimaryY = primaryY
          previousSecondX = secondX
          previousSecondY = secondY
        }
        handWasTracked = true
      } else {
        handWasTracked = false
      }
      const primaryVX = clampSigned((primaryX - previousPrimaryX) / Math.max(dt, 0.001), 2600)
      const primaryVY = clampSigned((primaryY - previousPrimaryY) / Math.max(dt, 0.001), 2600)
      const secondVX = clampSigned((secondX - previousSecondX) / Math.max(dt, 0.001), 2600)
      const secondVY = clampSigned((secondY - previousSecondY) / Math.max(dt, 0.001), 2600)
      previousPrimaryX = primaryX
      previousPrimaryY = primaryY
      previousSecondX = secondX
      previousSecondY = secondY

      const handWorldZ = -0.82 - (handOn ? hand.depth * 0.08 : 0)
      const handWorldX = (primaryX - cloudX) / objectScale
      const handWorldY = (primaryY - cloudY) / objectScale
      const secondWorldX = (secondX - cloudX) / objectScale
      const secondWorldY = (secondY - cloudY) / objectScale
      const handWorldVX = clampSigned(primaryVX / objectScale, 14)
      const handWorldVY = clampSigned(primaryVY / objectScale, 14)
      const secondWorldVX = clampSigned(secondVX / objectScale, 14)
      const secondWorldVY = clampSigned(secondVY / objectScale, 14)

      const push = handOn ? (5 + hand.energy * 14) * handInfluence : 0
      const pull = handOn ? hand.grab * 16 * handInfluence : 0
      const handRadius = 0.3 + (twoHands ? hand.span * 0.1 : hand.spread * 0.09) + hand.energy * 0.04
      const forceHands: ForceHand[] = []
      if (handInfluence > 0.01) {
        forceHands.push({
          x: handWorldX,
          y: handWorldY,
          z: handWorldZ,
          radius2: handRadius * handRadius,
          push,
          pull,
          vx: handWorldVX,
          vy: handWorldVY,
        })
        if (twoHands) {
          const secondRadius = 0.28 + hand.span * 0.08 + hand.energy * 0.03
          forceHands.push({
            x: secondWorldX,
            y: secondWorldY,
            z: handWorldZ,
            radius2: secondRadius * secondRadius,
            push: push * 0.9,
            pull: pull * 0.9,
            vx: secondWorldVX,
            vy: secondWorldVY,
          })
        }
      }

      // The whole cloud is dragged along the hand or pointer path. Opposite
      // wind makes particles lag behind, then the springs pull them back in.
      const windX = clampSigned((-cloudVX / objectScale) * 1.5, 12)
      const windY = clampSigned((-cloudVY / objectScale) * 1.5, 12)
      const loosen = handOn ? (twoHands ? hand.span : hand.spread) * handInfluence : 0
      const spring = 20 - loosen * 5
      const outward = handOn
        ? (burst * 3.6 * (0.62 + openness) + openness * 1.1) * handInfluence
        : 0
      const turbulence = reduced ? 0 : handOn ? hand.energy * 0.9 : motion.energy * 0.25
      const zScatter = Math.min(scatter, 1.68)
      const steps = dt > 0.022 ? 2 : 1
      const h = dt / steps
      const damping = Math.exp(-h * (3.7 - loosen * 0.9))

      for (let step = 0; step < steps; step += 1) {
        for (const particle of particles) {
          const homeX = particle.hx * scatter
          const homeY = particle.hy * scatter
          const homeZ = particle.hz * zScatter
          let ax = (homeX - particle.x) * spring
          let ay = (homeY - particle.y) * spring
          let az = (homeZ - particle.z) * spring

          if (Math.abs(windX) + Math.abs(windY) > 0.001) {
            ax += windX
            ay += windY
          }

          if (outward > 0.01) {
            const length =
              Math.sqrt(particle.x * particle.x + particle.y * particle.y + particle.z * particle.z) +
              0.001
            const radial = outward / length
            ax += particle.x * radial
            ay += particle.y * radial
            az += particle.z * radial
          }

          for (const forceHand of forceHands) {
            const dx = particle.x - forceHand.x
            const dy = particle.y - forceHand.y
            const dz = particle.z - forceHand.z
            const distance2 = dx * dx + dy * dy + dz * dz
            if (distance2 < forceHand.radius2 * 10) {
              const influence = Math.exp(-distance2 / forceHand.radius2)
              const distance = Math.sqrt(distance2) + 0.0001
              const force = (forceHand.push - forceHand.pull) * (influence / distance)
              ax += dx * force
              ay += dy * force
              az += dz * force
              // The wake is what visibly tears particles out of the sphere.
              ax += forceHand.vx * influence * 1.8 * handInfluence
              ay += forceHand.vy * influence * 1.8 * handInfluence
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
          if (particle.z < -1.55) particle.z = -1.55
          else if (particle.z > 2.4) particle.z = 2.4
          if (particle.x < -4.2) particle.x = -4.2
          else if (particle.x > 4.2) particle.x = 4.2
          if (particle.y < -4.2) particle.y = -4.2
          else if (particle.y > 4.2) particle.y = 4.2
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

      const fov = 3.1
      const cosYaw = Math.cos(yaw)
      const sinYaw = Math.sin(yaw)
      const cosPitch = Math.cos(pitch)
      const sinPitch = Math.sin(pitch)
      const cx = cloudX
      const cy = cloudY
      const dispersion = clamp01((scatter - 1) / 1.2)

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
        const alpha = (0.16 + nearness * 0.8) * (1 - dispersion * 0.22)
        const twinkle = 0.82 + Math.sin(time * 0.0013 + particle.seed) * 0.18
        const vertical = clamp01((particle.y + 1) / 2)
        const color = mix(warm, cool, 1 - vertical)
        const size = Math.max(0.55, particle.screenSize * 1.65 * (1 - dispersion * 0.18))

        if (particle.hasScreen) {
          const sx = particle.screenX - particle.sx
          const sy = particle.screenY - particle.sy
          const distance2 = sx * sx + sy * sy
          if (distance2 > 3.5) {
            // Cap trail length so a fast sweep leaves a streak, not a wall.
            const scale = Math.min(1, 48 / Math.sqrt(distance2))
            context.globalAlpha = alpha * 0.44 * twinkle
            context.strokeStyle = color
            context.lineWidth = Math.max(0.5, size * 0.6)
            context.beginPath()
            context.moveTo(particle.screenX - sx * scale, particle.screenY - sy * scale)
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

      // The open shell reveals a small signal core at its centre.
      if (dispersion > 0.01) {
        const coreRadius = 2 + openness * 3.5
        context.globalAlpha = 0.22 + dispersion * 0.5
        context.fillStyle = palette.brand
        context.beginPath()
        context.arc(cx, cy, coreRadius, 0, Math.PI * 2)
        context.fill()

        context.globalAlpha = 0.12 + dispersion * 0.3
        context.strokeStyle = palette.brand
        context.lineWidth = 0.8
        const arm = 8 + dispersion * 12
        context.beginPath()
        context.moveTo(cx - arm, cy)
        context.lineTo(cx - arm / 3, cy)
        context.moveTo(cx + arm / 3, cy)
        context.lineTo(cx + arm, cy)
        context.moveTo(cx, cy - arm)
        context.lineTo(cx, cy - arm / 3)
        context.moveTo(cx, cy + arm / 3)
        context.lineTo(cx, cy + arm)
        context.stroke()
      }

      // Hand feedback: a hairline field ring around each tracked hand.
      if (handOn && hand.confidence > 0.1) {
        const ringBase = Math.min(width, height)
        const ringRadius = ringBase * (0.045 + (twoHands ? hand.span * 0.07 : hand.spread * 0.1))
        drawRing(primaryX, primaryY, ringRadius, hand.confidence, hand.grab <= 0.5 && !twoHands)
        if (twoHands && hand.second) {
          const secondRadius = ringBase * (0.04 + hand.span * 0.05)
          drawRing(secondX, secondY, secondRadius, hand.confidence, false)
          context.globalAlpha = 0.12 + hand.span * 0.12
          context.strokeStyle = palette.brand
          context.lineWidth = 0.8
          context.setLineDash([2, 8])
          context.beginPath()
          context.moveTo(primaryX, primaryY)
          context.lineTo(secondX, secondY)
          context.stroke()
          context.setLineDash([])
        }
      }
      context.globalAlpha = 1

      raf = window.requestAnimationFrame(render)
    }

    // Fade the field away once the hero has scrolled out of view, and pause the
    // animation entirely while it is hidden.
    const visibilityObserver = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        const ratio = entry ? entry.intersectionRatio : 1
        heroVisible = ratio > 0.02
        canvas.style.opacity = `${Math.min(1, ratio * 1.8).toFixed(3)}`
        if (heroVisible && !visible) {
          visible = true
          lastTime = performance.now()
          raf = window.requestAnimationFrame(render)
        } else if (!heroVisible) {
          visible = false
        }
      },
      { threshold: [0, 0.05, 0.15, 0.3, 0.5, 0.75, 1] },
    )
    if (heroRef?.current) {
      visibilityObserver.observe(heroRef.current)
    } else {
      canvas.style.opacity = "1"
    }

    raf = window.requestAnimationFrame(render)

    return () => {
      window.cancelAnimationFrame(raf)
      resizeObserver.disconnect()
      themeObserver.disconnect()
      visibilityObserver.disconnect()
      motionQuery?.removeEventListener?.("change", onMotionPreference)
    }
  }, [field, heroRef])

  return <canvas ref={canvasRef} className={`asm-field-canvas ${className}`} aria-hidden="true" />
}
