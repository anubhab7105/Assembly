"use client"

import { useEffect, useRef } from "react"

const TRAIL_COUNT = 7

type TrailNode = {
  node: HTMLSpanElement | null
  x: number
  y: number
  ease: number
  depth: number
}

/**
 * A three-dimensional pointer: the dot tracks the hand, the ring lags and
 * tilts against its velocity, and seven ghost points trail at different
 * depths. It is decoration only and is disabled for touch and reduced motion.
 */
export function Cursor3D({ rootSelector = ".asm-landing" }: { rootSelector?: string }) {
  const layerRef = useRef<HTMLDivElement>(null)
  const dotRef = useRef<HTMLSpanElement>(null)
  const ringRef = useRef<HTMLSpanElement>(null)
  const labelRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (typeof window === "undefined") return
    if (!window.matchMedia?.("(pointer: fine)").matches) return
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return

    const root = document.querySelector<HTMLElement>(rootSelector)
    const layer = layerRef.current
    const dot = dotRef.current
    const ring = ringRef.current
    const label = labelRef.current
    if (!root || !layer || !dot || !ring || !label) return

    document.documentElement.classList.add("asm-cursor-enabled")

    let targetX = window.innerWidth / 2
    let targetY = window.innerHeight / 2
    let dotX = targetX
    let dotY = targetY
    let ringX = targetX
    let ringY = targetY
    let lastX = targetX
    let lastY = targetY
    let velocityX = 0
    let velocityY = 0
    let spin = 0
    let visible = false
    let raf = 0

    const trail: TrailNode[] = []
    for (let index = 0; index < TRAIL_COUNT; index += 1) {
      const node = document.createElement("span")
      node.className = "asm-cursor-trail"
      node.style.opacity = `${0.3 - index * 0.035}`
      layer.appendChild(node)
      trail.push({
        node,
        x: targetX,
        y: targetY,
        ease: 0.32 - index * 0.032,
        depth: index,
      })
    }

    const interactiveSelector = "a, button, summary, [data-cursor]"

    const onMove = (event: PointerEvent) => {
      targetX = event.clientX
      targetY = event.clientY
      if (!visible) {
        visible = true
        layer.style.opacity = "1"
      }
    }

    const onOver = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null
      const interactive = target?.closest<HTMLElement>(interactiveSelector)
      if (!interactive) return
      const text =
        interactive.getAttribute("data-cursor-label") ??
        (interactive.tagName === "A" ? "OPEN" : "SELECT")
      label.textContent = text
      layer.dataset.hover = "true"
    }

    const onOut = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null
      const interactive = target?.closest<HTMLElement>(interactiveSelector)
      if (!interactive) return
      const next = event.relatedTarget as HTMLElement | null
      if (next?.closest?.(interactiveSelector)) return
      layer.dataset.hover = "false"
    }

    const onLeave = () => {
      layer.style.opacity = "0"
      visible = false
    }

    const onEnter = () => {
      layer.style.opacity = "1"
      visible = true
    }

    const tick = () => {
      velocityX = targetX - lastX
      velocityY = targetY - lastY
      lastX = targetX
      lastY = targetY

      dotX += (targetX - dotX) * 0.62
      dotY += (targetY - dotY) * 0.62
      ringX += (targetX - ringX) * 0.18
      ringY += (targetY - ringY) * 0.18

      const speed = Math.min(40, Math.hypot(velocityX, velocityY))
      spin += speed * 0.22
      const tiltX = Math.max(-28, Math.min(28, velocityY * 1.15))
      const tiltY = Math.max(-28, Math.min(28, -velocityX * 1.15))
      const scale = 1 + speed * 0.008

      dot.style.transform = `translate3d(${dotX}px, ${dotY}px, 0) scale(${1 + speed * 0.006})`
      ring.style.transform = `translate3d(${ringX}px, ${ringY}px, 0) perspective(320px) rotateX(${tiltX}deg) rotateY(${tiltY}deg) rotateZ(${spin}deg) scale(${scale})`
      label.style.transform = `translate3d(${dotX}px, ${dotY}px, 0)`

      for (const node of trail) {
        node.x += (targetX - node.x) * node.ease
        node.y += (targetY - node.y) * node.ease
        const depthScale = 1 - node.depth * 0.07
        node.node?.style.setProperty(
          "transform",
          `translate3d(${node.x}px, ${node.y}px, ${-node.depth * 18}px) scale(${depthScale})`,
        )
      }

      raf = window.requestAnimationFrame(tick)
    }

    window.addEventListener("pointermove", onMove, { passive: true })
    window.addEventListener("pointerover", onOver, { passive: true })
    window.addEventListener("pointerout", onOut, { passive: true })
    document.addEventListener("pointerleave", onLeave)
    document.addEventListener("pointerenter", onEnter)
    raf = window.requestAnimationFrame(tick)

    return () => {
      document.documentElement.classList.remove("asm-cursor-enabled")
      window.cancelAnimationFrame(raf)
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerover", onOver)
      window.removeEventListener("pointerout", onOut)
      document.removeEventListener("pointerleave", onLeave)
      document.removeEventListener("pointerenter", onEnter)
      trail.forEach((item) => item.node?.remove())
    }
  }, [rootSelector])

  return (
    <div ref={layerRef} className="asm-cursor-layer" aria-hidden="true" style={{ opacity: 0 }}>
      <span ref={dotRef} className="asm-cursor" />
      <span ref={ringRef} className="asm-cursor-ring" />
      <span ref={labelRef} className="asm-cursor-label" />
    </div>
  )
}
