/**
 * Dependency-free hand approximation for the landing hero.
 *
 * A camera frame is downscaled to ~128×96, split into 4×4 cells, and scored
 * for skin-like colour plus frame-to-frame motion. The strongest connected
 * cluster becomes a hand candidate, and one-euro filters smooth the signal.
 *
 * This tracks a moving hand-shaped blob, not hand landmarks. Fingers cannot be
 * identified, so openness is approximated from how much of the blob's
 * bounding box is actually skin. Everything runs in this tab: frames are
 * never recorded, stored, or uploaded.
 */

export type HandBlob = {
  /** Normalised centre in the camera frame, 0..1 (unmirrored). */
  x: number
  y: number
  /** Longest bounding-box edge as a fraction of the frame. */
  size: number
  /** Skin cells / bounding-box area. Fists are dense; open hands are sparse. */
  fill: number
  /** Frame-to-frame motion inside the blob, 0..1. */
  motion: number
  confidence: number
  /** Number of connected cells, for tests and diagnostics. */
  area: number
}

export type HandDetection = HandBlob & {
  present: boolean
  /** The other hand while two hands are in frame. */
  second: HandBlob | null
}

export type HandPoint = {
  /** Mirrored position, -1..1, screen orientation. */
  x: number
  y: number
}

export type HandField = {
  present: boolean
  /** Control point: one hand, or the midpoint while two hands are tracked. */
  x: number
  y: number
  /** Apparent nearness from blob size, 0..1. */
  depth: number
  /** Openness proxy, 0..1. Two-hand span takes over when both are visible. */
  spread: number
  /** Closed-hand proxy, 0..1. */
  grab: number
  /** Motion inside the blob, 0..1. */
  energy: number
  confidence: number
  /** First hand position in mirrored screen coordinates. */
  first: HandPoint
  /** Second hand position while both hands are tracked. */
  second: HandPoint | null
  /** Distance between two hands, normalised 0..1. */
  span: number
}

export const EMPTY_HAND: HandField = {
  present: false,
  x: 0,
  y: 0,
  depth: 0,
  spread: 0,
  grab: 0,
  energy: 0,
  confidence: 0,
  first: { x: 0, y: 0 },
  second: null,
  span: 0,
}

/** Deep copy so callers can mutate the field without touching the constant. */
export function emptyHand(): HandField {
  return { ...EMPTY_HAND, first: { ...EMPTY_HAND.first }, second: null }
}

export function clamp01(value: number) {
  return Math.min(1, Math.max(0, value))
}

function clampSigned(value: number) {
  return Math.min(1, Math.max(-1, value))
}

function hueDegrees(r: number, g: number, b: number) {
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const chroma = max - min
  if (chroma === 0) return 0
  let hue: number
  if (max === r) hue = ((g - b) / chroma) % 6
  else if (max === g) hue = (b - r) / chroma + 2
  else hue = (r - g) / chroma + 4
  hue *= 60
  return hue < 0 ? hue + 360 : hue
}

/**
 * Soft skin-likelihood for one pixel, 0..1.
 *
 * A YCbCr gate and a warm-RGB gate must agree with a 0–58° hue window. The
 * confidence stays soft so the connected-component pass can prefer strongly
 * skin-coloured cells over borderline ones.
 */
export function skinConfidence(r: number, g: number, b: number): number {
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  if (max < 24) return 0

  const chroma = max - min
  const saturation = chroma / max

  const y = 0.299 * r + 0.587 * g + 0.114 * b
  const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
  const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b

  const ycbcr = cb > 70 && cb < 135 && cr > 128 && cr < 185 && y > 28
  const warmRgb = r > 45 && r > g + 6 && g >= b - 6 && saturation > 0.12 && saturation < 0.72
  if (!ycbcr && !warmRgb) return 0

  // Reject blue/green-dominant pixels that slip past the gates under mixed light.
  if (b > r + 12 || g > r + 10) return 0

  const hue = hueDegrees(r, g, b)
  if (hue > 58 && hue < 330) return 0

  const saturationGate = clamp01((saturation - 0.09) / 0.12)
  const toneGate = clamp01((max - 26) / 24)
  const warmth = clamp01((r - b) / 40)
  return clamp01(0.45 + saturationGate * 0.25 + toneGate * 0.15 + warmth * 0.15)
}

export type OneEuroFilter = ((value: number, timestampMs: number) => number) & {
  reset: () => void
}

function smoothingFactor(dtSeconds: number, cutoffHz: number) {
  const tau = 1 / (2 * Math.PI * cutoffHz)
  return 1 / (1 + tau / dtSeconds)
}

/**
 * One-euro filter: low jitter when still, low lag when moving fast.
 * Timestamps are in milliseconds, matching performance.now().
 */
export function createOneEuroFilter(minCutoff: number, beta: number, derivativeCutoff = 1): OneEuroFilter {
  let previous: number | null = null
  let previousDerivative = 0
  let previousTime = 0

  const filter = ((value: number, timestampMs: number) => {
    const dt = previous === null ? 1 / 60 : Math.min(0.25, Math.max(1 / 240, (timestampMs - previousTime) / 1000))
    const derivative = previous === null ? 0 : (value - previous) / dt
    const derivativeAlpha = smoothingFactor(dt, derivativeCutoff)
    previousDerivative += derivativeAlpha * (derivative - previousDerivative)
    const cutoff = minCutoff + beta * Math.abs(previousDerivative)
    const alpha = smoothingFactor(dt, cutoff)
    const next = previous === null ? value : previous + alpha * (value - previous)
    previous = next
    previousTime = timestampMs
    return next
  }) as OneEuroFilter

  filter.reset = () => {
    previous = null
    previousDerivative = 0
    previousTime = 0
  }
  return filter
}

const CELL = 4
const SKIN_THRESHOLD = 0.24
const MIN_CELLS = 3
const MAX_AREA_FRACTION = 0.55

type Candidate = {
  x: number
  y: number
  size: number
  fill: number
  motion: number
  confidence: number
  area: number
  baseScore: number
  score: number
}

type Previous = {
  x: number
  y: number
  area: number
  at: number
}

/**
 * Frame-to-frame hand candidate detector. Reuses all buffers; call process()
 * once per camera frame with an RGBA buffer.
 */
export class HandTracker {
  private cols = 0
  private rows = 0
  private cells = 0
  private width = 0
  private height = 0

  private skin = new Float32Array(0)
  private motion = new Float32Array(0)
  private counts = new Uint16Array(0)
  private mask = new Uint8Array(0)
  private visited = new Uint8Array(0)
  private stack = new Int32Array(0)
  private gray: Uint8Array = new Uint8Array(0)
  private previousGray: Uint8Array | null = null
  private previous: Previous | null = null

  private allocate(width: number, height: number) {
    this.width = width
    this.height = height
    this.cols = Math.ceil(width / CELL)
    this.rows = Math.ceil(height / CELL)
    this.cells = this.cols * this.rows
    this.skin = new Float32Array(this.cells)
    this.motion = new Float32Array(this.cells)
    this.counts = new Uint16Array(this.cells)
    this.mask = new Uint8Array(this.cells)
    this.visited = new Uint8Array(this.cells)
    this.stack = new Int32Array(this.cells)
    this.gray = new Uint8Array(width * height)
    this.previousGray = null
  }

  reset() {
    this.previous = null
    this.previousGray = null
  }

  process(rgba: Uint8ClampedArray, width: number, height: number, timestampMs: number): HandDetection {
    if (width !== this.width || height !== this.height) this.allocate(width, height)

    const { cols, rows, cells } = this
    this.skin.fill(0)
    this.motion.fill(0)
    this.counts.fill(0)
    this.mask.fill(0)
    this.visited.fill(0)

    const previousGray = this.previousGray
    for (let y = 0; y < height; y += 1) {
      const row = (y / CELL) | 0
      for (let x = 0; x < width; x += 1) {
        const offset = (y * width + x) * 4
        const r = rgba[offset]
        const g = rgba[offset + 1]
        const b = rgba[offset + 2]
        const gray = (r * 77 + g * 150 + b * 29) >> 8
        const pixel = y * width + x
        this.gray[pixel] = gray

        const cell = row * cols + ((x / CELL) | 0)
        this.counts[cell] += 1
        const confidence = skinConfidence(r, g, b)
        if (confidence > 0) this.skin[cell] += confidence

        if (previousGray) {
          const delta = gray - previousGray[pixel]
          if (delta > 16 || delta < -16) this.motion[cell] += 1
        }
      }
    }

    for (let cell = 0; cell < cells; cell += 1) {
      const pixels = this.counts[cell]
      if (pixels === 0) continue
      if (this.skin[cell] / pixels >= SKIN_THRESHOLD) this.mask[cell] = 1
    }

    const candidates: Candidate[] = []
    for (let start = 0; start < cells; start += 1) {
      if (this.mask[start] === 0 || this.visited[start] === 1) continue

      let top = 0
      this.stack[top++] = start
      this.visited[start] = 1

      let area = 0
      let weightSum = 0
      let weightedX = 0
      let weightedY = 0
      let motionSum = 0
      let skinSum = 0
      let minX = cols
      let maxX = -1
      let minY = rows
      let maxY = -1

      while (top > 0) {
        const cell = this.stack[--top]
        area += 1
        const col = cell % cols
        const row = (cell / cols) | 0
        if (col < minX) minX = col
        if (col > maxX) maxX = col
        if (row < minY) minY = row
        if (row > maxY) maxY = row

        const pixels = this.counts[cell] || 1
        const confidence = this.skin[cell] / pixels
        const move = Math.min(1, this.motion[cell] / pixels)
        const weight = confidence * (0.45 + 1.9 * move)
        weightSum += weight
        weightedX += (col + 0.5) * weight
        weightedY += (row + 0.5) * weight
        motionSum += this.motion[cell]
        skinSum += this.skin[cell]

        for (let dy = -1; dy <= 1; dy += 1) {
          for (let dx = -1; dx <= 1; dx += 1) {
            if (dx === 0 && dy === 0) continue
            const nextCol = col + dx
            const nextRow = row + dy
            if (nextCol < 0 || nextRow < 0 || nextCol >= cols || nextRow >= rows) continue
            const next = nextRow * cols + nextCol
            if (this.mask[next] === 1 && this.visited[next] === 0) {
              this.visited[next] = 1
              this.stack[top++] = next
            }
          }
        }
      }

      if (area < MIN_CELLS || weightSum <= 0) continue
      const areaFraction = area / cells
      if (areaFraction > MAX_AREA_FRACTION) continue

      const boxWidth = maxX - minX + 1
      const boxHeight = maxY - minY + 1
      const size = Math.max(boxWidth / cols, boxHeight / rows)
      const fill = area / (boxWidth * boxHeight)
      const motionAverage = Math.min(1, motionSum / (area * CELL * CELL))
      const skinAverage = Math.min(1, skinSum / (area * CELL * CELL))
      const x = weightedX / weightSum / cols
      const y = weightedY / weightSum / rows

      const aspect = Math.max(boxWidth, boxHeight) / Math.max(1, Math.min(boxWidth, boxHeight))
      const shape = 1 / (1 + Math.max(0, aspect - 3.4) * 0.6)

      let prior = 1
      if (this.previous && timestampMs - this.previous.at < 500) {
        const distance = Math.hypot(x - this.previous.x, y - this.previous.y)
        prior = 0.12 + 0.88 * Math.exp(-(distance * distance) / (2 * 0.26 * 0.26))
        // A still, distant blob is usually a face or background, not the hand.
        if (distance > 0.38 && motionAverage < 0.02 && area < this.previous.area * 2) prior *= 0.05
      } else {
        // On first acquisition, hands usually sit below the face.
        prior = 0.65 + 0.35 * clamp01((y - 0.3) / 0.45)
      }

      const baseScore = Math.sqrt(area) * (0.5 + 2.4 * Math.min(1, motionAverage * 3)) * shape
      candidates.push({
        x,
        y,
        size,
        fill,
        motion: motionAverage,
        confidence: clamp01(skinAverage * 0.75 + Math.min(1, motionAverage * 3) * 0.2 + Math.min(1, area / 25) * 0.15),
        area,
        baseScore,
        score: baseScore * prior,
      })
    }

    // Keep this frame's gray buffer for the next diff, and recycle the old one.
    this.previousGray = this.gray
    this.gray = previousGray ?? new Uint8Array(width * height)

    let best: Candidate | null = null
    for (const candidate of candidates) {
      if (best === null || candidate.score > best.score) best = candidate
    }

    if (!best) {
      if (this.previous && timestampMs - this.previous.at > 500) this.previous = null
      return { present: false, x: 0.5, y: 0.5, size: 0, fill: 0, motion: 0, confidence: 0, area: 0, second: null }
    }

    // A second, well-separated hand enables the spread/open gesture. Rank it
    // by motion and lower-frame position so a still face is not mistaken for it.
    let second: Candidate | null = null
    let secondScore = 0
    for (const candidate of candidates) {
      if (candidate === best) continue
      const distance = Math.hypot(candidate.x - best.x, candidate.y - best.y)
      if (distance < 0.15 || candidate.confidence < 0.16) continue
      const lowerFrame = 0.45 + 0.55 * clamp01((candidate.y - 0.18) / 0.5)
      const score = candidate.baseScore * lowerFrame
      if (score > secondScore) {
        secondScore = score
        second = candidate
      }
    }

    this.previous = { x: best.x, y: best.y, area: best.area, at: timestampMs }
    return {
      present: true,
      x: best.x,
      y: best.y,
      size: best.size,
      fill: best.fill,
      motion: best.motion,
      confidence: best.confidence,
      area: best.area,
      second: second
        ? {
            x: second.x,
            y: second.y,
            size: second.size,
            fill: second.fill,
            motion: second.motion,
            confidence: second.confidence,
            area: second.area,
          }
        : null,
    }
  }
}

/**
 * Turns noisy per-frame detections into the smoothed hand field consumed by
 * the particle cloud. Presence is hysteretic so a single dropped frame does not
 * make the sphere jump.
 */
export class HandSmoother {
  private filterX = createOneEuroFilter(1.35, 0.06)
  private filterY = createOneEuroFilter(1.35, 0.06)
  private filterMidX = createOneEuroFilter(1.35, 0.06)
  private filterMidY = createOneEuroFilter(1.35, 0.06)
  private filterOffsetX = createOneEuroFilter(1.5, 0.05)
  private filterOffsetY = createOneEuroFilter(1.5, 0.05)
  private filterSpan = createOneEuroFilter(1.2, 0.03)
  private filterDepth = createOneEuroFilter(0.7, 0.012)
  private filterSpread = createOneEuroFilter(0.8, 0.01)
  private filterGrab = createOneEuroFilter(0.95, 0.012)
  private filterEnergy = createOneEuroFilter(1.5, 0.035)
  private filterConfidence = createOneEuroFilter(0.9, 0.012)
  private state: HandField = emptyHand()
  private present = false
  private hits = 0
  private misses = 0
  private secondPresent = false
  private secondHits = 0
  private secondMisses = 0
  private mode: "none" | "single" | "two" = "none"
  private lastRawX = 0.5
  private lastRawY = 0.5
  private lastRawAt = 0

  reset() {
    this.filterX.reset()
    this.filterY.reset()
    this.filterMidX.reset()
    this.filterMidY.reset()
    this.filterOffsetX.reset()
    this.filterOffsetY.reset()
    this.filterSpan.reset()
    this.filterDepth.reset()
    this.filterSpread.reset()
    this.filterGrab.reset()
    this.filterEnergy.reset()
    this.filterConfidence.reset()
    this.state = emptyHand()
    this.present = false
    this.hits = 0
    this.misses = 0
    this.secondPresent = false
    this.secondHits = 0
    this.secondMisses = 0
    this.mode = "none"
    this.lastRawAt = 0
  }

  update(raw: HandDetection, timestampMs: number): HandField {
    if (!raw.present) {
      this.hits = 0
      this.misses += 1
      if (this.misses > 10) this.present = false
      this.secondHits = 0
      this.secondMisses += 1
      if (this.secondMisses > 5) {
        this.secondPresent = false
        this.mode = "none"
        this.state.second = null
        this.state.span = 0
        this.state.first = { x: this.state.x, y: this.state.y }
      }
      if (this.misses > 24) this.reset()
      this.state.present = this.present
      return this.state
    }

    this.hits += 1
    this.misses = 0
    if (this.hits >= 2) this.present = true

    if (raw.second) {
      this.secondHits += 1
      this.secondMisses = 0
      if (this.secondHits >= 2) this.secondPresent = true
    } else {
      this.secondHits = 0
      this.secondMisses += 1
      if (this.secondMisses > 5) {
        this.secondPresent = false
        this.mode = "none"
        this.state.second = null
        this.state.span = 0
        this.state.first = { x: this.state.x, y: this.state.y }
      }
    }

    const dt = this.lastRawAt === 0 ? 1 / 30 : Math.max(0.001, (timestampMs - this.lastRawAt) / 1000)
    const speed = Math.hypot(raw.x - this.lastRawX, raw.y - this.lastRawY) / dt
    this.lastRawX = raw.x
    this.lastRawY = raw.y
    this.lastRawAt = timestampMs

    // While the second hand flickers, hold the last two-hand pose instead of
    // collapsing the gesture on a single dropped detection.
    if (this.secondPresent && !raw.second) {
      this.state.present = this.present
      return this.state
    }

    const depth = clamp01((raw.size - 0.12) / 0.34)
    const energy = clamp01(raw.motion * 1.6 + speed * 0.35)
    const confidence = this.filterConfidence(raw.confidence, timestampMs)

    if (this.secondPresent && raw.second) {
      if (this.mode !== "two") {
        this.filterMidX.reset()
        this.filterMidY.reset()
        this.filterOffsetX.reset()
        this.filterOffsetY.reset()
        this.filterSpan.reset()
        this.mode = "two"
      }

      const ax = clampSigned((0.5 - raw.x) * 2.4)
      const ay = clampSigned((raw.y - 0.5) * 2.4)
      const bx = clampSigned((0.5 - raw.second.x) * 2.4)
      const by = clampSigned((raw.second.y - 0.5) * 2.4)
      const firstX = Math.min(ax, bx)
      const firstY = ax <= bx ? ay : by
      const secondX = Math.max(ax, bx)
      const secondY = ax <= bx ? by : ay
      const midX = (firstX + secondX) / 2
      const midY = (firstY + secondY) / 2
      const offsetX = secondX - firstX
      const offsetY = secondY - firstY
      const distance = Math.hypot(offsetX, offsetY)

      const smoothMidX = this.filterMidX(midX, timestampMs)
      const smoothMidY = this.filterMidY(midY, timestampMs)
      const smoothOffsetX = this.filterOffsetX(offsetX, timestampMs)
      const smoothOffsetY = this.filterOffsetY(offsetY, timestampMs)
      const span = this.filterSpan(clamp01((distance - 0.3) / 1.2), timestampMs)

      this.state = {
        present: this.present,
        x: smoothMidX,
        y: smoothMidY,
        depth: this.filterDepth(Math.max(depth, clamp01((raw.second.size - 0.12) / 0.34)), timestampMs),
        spread: span,
        grab: clamp01(1 - span),
        energy: this.filterEnergy(
          Math.max(energy, clamp01(raw.second.motion * 1.6 + speed * 0.35)),
          timestampMs,
        ),
        confidence: Math.max(confidence, raw.second.confidence),
        first: {
          x: smoothMidX - smoothOffsetX / 2,
          y: smoothMidY - smoothOffsetY / 2,
        },
        second: {
          x: smoothMidX + smoothOffsetX / 2,
          y: smoothMidY + smoothOffsetY / 2,
        },
        span,
      }
      return this.state
    }

    if (this.mode !== "single") {
      this.filterX.reset()
      this.filterY.reset()
      this.mode = "single"
    }

    const x = clampSigned((0.5 - raw.x) * 2.4)
    const y = clampSigned((raw.y - 0.5) * 2.4)
    const smoothX = this.filterX(x, timestampMs)
    const smoothY = this.filterY(y, timestampMs)
    // Bounding-box fill separates a spread hand from a fist. The windows do
    // not overlap, so a hand is never pulled and pushed at the same time.
    const spread = clamp01((0.85 - raw.fill) / 0.4)
    const grab = clamp01((raw.fill - 0.68) / 0.22)

    this.state = {
      present: this.present,
      x: smoothX,
      y: smoothY,
      depth: this.filterDepth(depth, timestampMs),
      spread: this.filterSpread(spread, timestampMs),
      grab: this.filterGrab(grab, timestampMs),
      energy: this.filterEnergy(energy, timestampMs),
      confidence,
      first: { x: smoothX, y: smoothY },
      second: null,
      span: 0,
    }
    return this.state
  }
}
