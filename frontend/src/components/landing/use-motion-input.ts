"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  emptyHand,
  HandSmoother,
  HandTracker,
  type HandField,
} from "@/lib/hand-tracker"

export type MotionSource = "pointer" | "sensor" | "camera"

export type MotionField = {
  /** Smoothed position in the -1..1 range. */
  x: number
  y: number
  /** Un-smoothed target, useful for snappier UI accents. */
  targetX: number
  targetY: number
  /** How much movement the camera is currently seeing (0..1). */
  energy: number
  source: MotionSource
  /** True while a pointer is actively steering the field. */
  pointerActive: boolean
  /** Hand tracking state; present is only true while a hand is in frame. */
  hand: HandField
}

export type CameraState = "off" | "requesting" | "on" | "error" | "unsupported"
export type SensorState = "off" | "available" | "on" | "denied" | "unsupported"

const EMPTY_FIELD: MotionField = {
  x: 0,
  y: 0,
  targetX: 0,
  targetY: 0,
  energy: 0,
  source: "pointer",
  pointerActive: false,
  hand: emptyHand(),
}

type PermissionCapableEvent = typeof DeviceOrientationEvent & {
  requestPermission?: () => Promise<"granted" | "denied">
}

type VideoFrameVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (callback: (now: number, metadata: unknown) => void) => number
  cancelVideoFrameCallback?: (handle: number) => void
}

type Analysis = {
  canvas: HTMLCanvasElement
  context: CanvasRenderingContext2D
  tracker: HandTracker
  smoother: HandSmoother
}

const ANALYSIS_WIDTH = 128
const ANALYSIS_HEIGHT = 96
const FALLBACK_INTERVAL_MS = 33

function clamp(value: number, min = -1, max = 1) {
  return Math.min(max, Math.max(min, value))
}

function prefersReducedMotion() {
  if (typeof window === "undefined") return false
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false
}

/**
 * One shared motion field for the landing experience.
 *
 * Priority: camera hand-tracking → device orientation → pointer.
 * Camera frames never leave the browser: they are downscaled to 128×96 and
 * reduced to a skin/motion blob on the device. No frame is recorded or sent.
 */
export function useMotionInput(options: {
  rootRef?: React.RefObject<HTMLElement | null>
  enabled?: boolean
} = {}) {
  const { rootRef, enabled = true } = options
  const fieldRef = useRef<MotionField>({
    ...EMPTY_FIELD,
    hand: emptyHand(),
  })

  const pointerTarget = useRef({ x: 0, y: 0 })
  const pointerActiveRef = useRef(false)
  const sensorTarget = useRef({ x: 0, y: 0 })
  const cameraHandRef = useRef<HandField>(emptyHand())

  const [cameraState, setCameraState] = useState<CameraState>("off")
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [handActive, setHandActive] = useState(false)
  const [sensorState, setSensorState] = useState<SensorState>("off")

  const streamRef = useRef<MediaStream | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const analysisRef = useRef<Analysis | null>(null)
  const stopSamplingRef = useRef<(() => void) | null>(null)
  const lastAnalysisRef = useRef(0)
  const handPresenceRef = useRef(false)
  const mountedRef = useRef(true)
  const sensorSeenRef = useRef(false)
  const reducedRef = useRef(false)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const publishHandPresence = useCallback((next: boolean) => {
    if (handPresenceRef.current === next) return
    handPresenceRef.current = next
    setHandActive(next)
  }, [])

  const stopCamera = useCallback(() => {
    stopSamplingRef.current?.()
    stopSamplingRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) {
      videoRef.current.srcObject = null
      videoRef.current.remove()
      videoRef.current = null
    }
    analysisRef.current = null
    cameraHandRef.current = emptyHand()
    handPresenceRef.current = false
    setHandActive(false)
    setCameraState("off")
  }, [])

  const disableCamera = useCallback(() => {
    stopCamera()
    setCameraError(null)
  }, [stopCamera])

  const analyseFrame = useCallback(
    (timestampMs: number) => {
      const video = videoRef.current
      const analysis = analysisRef.current
      if (!video || !analysis || video.readyState < 2) return
      // Some webcams deliver 60 fps; the tracker is stable at 30 and the
      // saved frame time goes into the transition smoothing.
      if (timestampMs - lastAnalysisRef.current < 24) return
      lastAnalysisRef.current = timestampMs

      analysis.context.drawImage(video, 0, 0, ANALYSIS_WIDTH, ANALYSIS_HEIGHT)
      let image: ImageData
      try {
        image = analysis.context.getImageData(0, 0, ANALYSIS_WIDTH, ANALYSIS_HEIGHT)
      } catch {
        return
      }

      const raw = analysis.tracker.process(image.data, ANALYSIS_WIDTH, ANALYSIS_HEIGHT, timestampMs)
      const hand = analysis.smoother.update(raw, timestampMs)
      cameraHandRef.current = hand
      publishHandPresence(hand.present)
    },
    [publishHandPresence],
  )

  const startSampling = useCallback(
    (video: HTMLVideoElement) => {
      const frameVideo = video as VideoFrameVideo
      if (typeof frameVideo.requestVideoFrameCallback === "function") {
        let stopped = false
        let handle = 0
        const step = (now: number) => {
          if (stopped) return
          analyseFrame(now)
          handle = frameVideo.requestVideoFrameCallback?.(step) ?? 0
        }
        handle = frameVideo.requestVideoFrameCallback?.(step) ?? 0
        stopSamplingRef.current = () => {
          stopped = true
          frameVideo.cancelVideoFrameCallback?.(handle)
        }
        return
      }

      const timer = window.setInterval(() => analyseFrame(performance.now()), FALLBACK_INTERVAL_MS)
      stopSamplingRef.current = () => window.clearInterval(timer)
    },
    [analyseFrame],
  )

  const toggleCamera = useCallback(async () => {
    if (cameraState === "on" || cameraState === "requesting") {
      disableCamera()
      return
    }
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setCameraState("unsupported")
      setCameraError("This browser cannot access a camera. Pointer and motion input still work.")
      return
    }

    setCameraState("requesting")
    setCameraError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 640 },
          height: { ideal: 480 },
          frameRate: { ideal: 30, max: 30 },
        },
        audio: false,
      })

      // The permission prompt can outlive the page; never keep the camera light
      // on after an unmount.
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }

      const canvas = document.createElement("canvas")
      canvas.width = ANALYSIS_WIDTH
      canvas.height = ANALYSIS_HEIGHT
      const context = canvas.getContext("2d", { willReadFrequently: true })
      if (!context) {
        stream.getTracks().forEach((track) => track.stop())
        throw new Error("Canvas 2D is unavailable")
      }

      const video = document.createElement("video")
      video.playsInline = true
      video.muted = true
      video.autoplay = true
      video.style.position = "fixed"
      video.style.opacity = "0"
      video.style.pointerEvents = "none"
      video.style.width = "1px"
      video.style.height = "1px"
      video.style.top = "0"
      video.style.left = "0"
      video.srcObject = stream
      document.body.appendChild(video)
      await video.play().catch(() => {})

      if (!mountedRef.current) {
        video.remove()
        stream.getTracks().forEach((track) => track.stop())
        return
      }

      videoRef.current = video
      streamRef.current = stream
      analysisRef.current = {
        canvas,
        context,
        tracker: new HandTracker(),
        smoother: new HandSmoother(),
      }
      cameraHandRef.current = emptyHand()
      handPresenceRef.current = false
      lastAnalysisRef.current = 0
      setHandActive(false)
      setCameraState("on")
      startSampling(video)

      stream.getVideoTracks().forEach((track) => {
        track.onended = () => {
          if (mountedRef.current) disableCamera()
        }
      })
    } catch (error) {
      const name = error instanceof DOMException ? error.name : ""
      setCameraState("error")
      setCameraError(
        name === "NotAllowedError"
          ? "Camera permission was declined. Pointer and motion input still work."
          : name === "NotFoundError"
            ? "No camera was found. Pointer and motion input still work."
            : "The camera could not start. Pointer and motion input still work.",
      )
    }
  }, [cameraState, disableCamera, startSampling])

  const enableSensors = useCallback(async () => {
    if (typeof window === "undefined" || typeof DeviceOrientationEvent === "undefined") {
      setSensorState("unsupported")
      return
    }
    const ctor = DeviceOrientationEvent as PermissionCapableEvent
    if (typeof ctor.requestPermission === "function") {
      try {
        const permission = await ctor.requestPermission()
        if (permission !== "granted") {
          setSensorState("denied")
          return
        }
      } catch {
        setSensorState("denied")
        return
      }
    }
    sensorSeenRef.current = false
    setSensorState("available")
  }, [])

  const toggleSensors = useCallback(() => {
    if (sensorState === "on") {
      setSensorState("off")
      sensorTarget.current = { x: 0, y: 0 }
      return
    }
    void enableSensors()
  }, [enableSensors, sensorState])

  // Pointer input
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return
    reducedRef.current = prefersReducedMotion()
    const reduceQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)")
    const onReduceChange = () => {
      reducedRef.current = prefersReducedMotion()
    }
    reduceQuery?.addEventListener?.("change", onReduceChange)

    const onPointer = (event: PointerEvent) => {
      pointerActiveRef.current = true
      pointerTarget.current = {
        x: clamp((event.clientX / window.innerWidth) * 2 - 1),
        y: clamp((event.clientY / window.innerHeight) * 2 - 1),
      }
    }
    const onLeave = () => {
      pointerActiveRef.current = false
      pointerTarget.current = { x: 0, y: 0 }
    }
    const onPointerUp = (event: PointerEvent) => {
      if (event.pointerType === "mouse") return
      onLeave()
    }

    window.addEventListener("pointermove", onPointer, { passive: true })
    document.addEventListener("pointerleave", onLeave)
    window.addEventListener("pointerup", onPointerUp)
    window.addEventListener("blur", onLeave)

    return () => {
      reduceQuery?.removeEventListener?.("change", onReduceChange)
      window.removeEventListener("pointermove", onPointer)
      document.removeEventListener("pointerleave", onLeave)
      window.removeEventListener("pointerup", onPointerUp)
      window.removeEventListener("blur", onLeave)
    }
  }, [enabled])

  // Device orientation input
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return
    const onOrientation = (event: DeviceOrientationEvent) => {
      if (event.gamma === null && event.beta === null) return
      sensorSeenRef.current = true
      const gamma = clamp(event.gamma ?? 0, -35, 35)
      const beta = clamp((event.beta ?? 45) - 45, -35, 35)
      sensorTarget.current = {
        x: clamp(gamma / 26),
        y: clamp(-beta / 30),
      }
      setSensorState((current) => (current === "on" ? current : "on"))
    }
    window.addEventListener("deviceorientation", onOrientation)
    return () => window.removeEventListener("deviceorientation", onOrientation)
  }, [enabled])

  // Shared smoothing loop, also publishes CSS variables for depth layers.
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return
    let raf = 0
    let lastTime = performance.now()

    const tick = (time: number) => {
      const dt = Math.min(0.05, Math.max(0.001, (time - lastTime) / 1000))
      lastTime = time

      const cameraOn = cameraState === "on"
      const sensorOn = sensorState === "on"
      const hand = cameraHandRef.current
      const handOn = cameraOn && hand.present
      const pointerOn = !cameraOn && !sensorOn && pointerActiveRef.current
      const field = fieldRef.current

      // While the camera is searching, the field settles to centre instead of
      // falling back to pointer steering (which would fight the hand).
      let targetX = 0
      let targetY = 0
      let rate = 2.4
      if (handOn) {
        targetX = hand.x
        targetY = hand.y
        rate = 15
      } else if (!cameraOn && sensorOn) {
        targetX = sensorTarget.current.x
        targetY = sensorTarget.current.y
        rate = 9
      } else if (pointerOn) {
        targetX = pointerTarget.current.x
        targetY = pointerTarget.current.y
        rate = 9
      }

      const easing = reducedRef.current ? 1 : 1 - Math.exp(-dt * rate)
      field.x += (targetX - field.x) * easing
      field.y += (targetY - field.y) * easing
      field.targetX = targetX
      field.targetY = targetY
      field.source = cameraOn ? "camera" : sensorOn ? "sensor" : "pointer"
      field.pointerActive = pointerOn

      if (handOn) {
        field.hand.present = true
        field.hand.x = hand.x
        field.hand.y = hand.y
        field.hand.depth = hand.depth
        field.hand.spread = hand.spread
        field.hand.grab = hand.grab
        field.hand.energy = hand.energy
        field.hand.confidence = hand.confidence
        field.hand.first.x = hand.first.x
        field.hand.first.y = hand.first.y
        if (hand.second) {
          if (!field.hand.second) field.hand.second = { x: 0, y: 0 }
          field.hand.second.x = hand.second.x
          field.hand.second.y = hand.second.y
        } else {
          field.hand.second = null
        }
        field.hand.span = hand.span
        field.energy = hand.energy
      } else {
        field.hand.present = false
        field.hand.x = 0
        field.hand.y = 0
        field.hand.depth = 0
        field.hand.spread = 0
        field.hand.grab = 0
        field.hand.energy = 0
        field.hand.confidence = 0
        field.hand.first.x = 0
        field.hand.first.y = 0
        field.hand.second = null
        field.hand.span = 0
        field.energy *= Math.exp(-dt * 3)
      }

      if (rootRef?.current) {
        rootRef.current.style.setProperty("--px", field.x.toFixed(4))
        rootRef.current.style.setProperty("--py", field.y.toFixed(4))
        rootRef.current.style.setProperty("--px-deg", `${(field.x * 3.2).toFixed(2)}deg`)
        rootRef.current.style.setProperty("--py-deg", `${(-field.y * 3.2).toFixed(2)}deg`)
      }

      raf = window.requestAnimationFrame(tick)
    }
    raf = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(raf)
  }, [cameraState, enabled, rootRef, sensorState])

  useEffect(() => {
    return () => {
      stopCamera()
    }
  }, [stopCamera])

  return {
    field: fieldRef,
    cameraState,
    cameraError,
    cameraActive: cameraState === "on",
    handActive,
    toggleCamera,
    disableCamera,
    sensorState,
    sensorActive: sensorState === "on",
    toggleSensors,
  }
}
