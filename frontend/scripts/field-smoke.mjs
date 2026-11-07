/**
 * Manual smoke check for the landing particle field.
 *
 * Requires the dev server (default http://localhost:3000). It fakes a camera
 * with a synthetic skin-coloured canvas stream, exercises pointer, one-hand and
 * two-hand input, then captures scroll-fade and mobile states. Screenshots are
 * written to %TEMP%. No frames, files, or keys leave the machine.
 *
 *   node scripts/field-smoke.mjs
 *   FIELD_SMOKE_URL=http://localhost:3001 node scripts/field-smoke.mjs
 */
import { chromium } from "@playwright/test"

const base = process.env.FIELD_SMOKE_URL ?? "http://localhost:3000"
const out = process.env.TEMP ?? "."
const browser = await chromium.launch()
const errors = []

function watch(page) {
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`)
  })
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`))
}

async function fakeCamera(page) {
  await page.addInitScript(() => {
    const canvas = document.createElement("canvas")
    canvas.width = 640
    canvas.height = 480
    const context = canvas.getContext("2d")
    const draw = () => {
      context.fillStyle = "#7d8a99"
      context.fillRect(0, 0, canvas.width, canvas.height)
      const hands = window.__hands ?? []
      for (const hand of hands) {
        const gradient = context.createRadialGradient(hand.x, hand.y, 2, hand.x, hand.y, hand.r)
        gradient.addColorStop(0, "#d2a082")
        gradient.addColorStop(1, "#b07c5e")
        context.fillStyle = gradient
        context.beginPath()
        context.ellipse(hand.x, hand.y, hand.r, hand.r * 1.25, 0, 0, Math.PI * 2)
        context.fill()
      }
      requestAnimationFrame(draw)
    }
    draw()

    const stream = canvas.captureStream(30)
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: async () => stream },
    })
    window.__setHands = (hands) => {
      window.__hands = hands
    }
  })
}

async function dismissCookie(page) {
  const gotIt = page.getByRole("button", { name: "Got it" })
  // The dev-tools indicator sits over the banner on narrow viewports, so
  // dispatch the click directly instead of aiming at coordinates.
  if (await gotIt.count()) await gotIt.evaluate((node) => node.click())
  await page.waitForTimeout(300)
}

const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
watch(page)
await fakeCamera(page)
await page.goto(base, { waitUntil: "networkidle" })
await page.waitForTimeout(2500)
await dismissCookie(page)
await page.screenshot({ path: `${out}\\assembly-field-rest.png` })

// Pointer control: move the cursor to the lower left, then upper right.
await page.mouse.move(300, 700, { steps: 24 })
await page.waitForTimeout(1400)
await page.screenshot({ path: `${out}\\assembly-pointer-left.png` })
await page.mouse.move(1200, 220, { steps: 24 })
await page.waitForTimeout(1400)
await page.screenshot({ path: `${out}\\assembly-pointer-right.png` })

// Camera control with a synthetic skin-coloured video stream.
const cameraButton = page.locator('button[title="Use the camera to track your hand locally"]')
await cameraButton.click()
await page.waitForTimeout(800)

// One hand, centred, then sweeping left.
await page.evaluate(() => window.__setHands([{ x: 320, y: 300, r: 46 }]))
await page.waitForTimeout(1800)
await page.screenshot({ path: `${out}\\assembly-hand-center.png` })

await page.evaluate(() => window.__setHands([{ x: 150, y: 280, r: 46 }]))
await page.waitForTimeout(1600)
await page.screenshot({ path: `${out}\\assembly-hand-left.png` })

// Two hands apart, then close together.
await page.evaluate(() =>
  window.__setHands([
    { x: 180, y: 300, r: 46 },
    { x: 460, y: 300, r: 46 },
  ]),
)
await page.waitForTimeout(2200)
await page.screenshot({ path: `${out}\\assembly-hand-open.png` })

await page.evaluate(() =>
  window.__setHands([
    { x: 280, y: 300, r: 30 },
    { x: 380, y: 300, r: 30 },
  ]),
)
await page.waitForTimeout(2200)
await page.screenshot({ path: `${out}\\assembly-hand-closed.png` })

// The landing scrolls inside the app shell, not the window.
await page.evaluate(() => {
  const landing = document.querySelector(".asm-landing")
  landing?.parentElement?.scrollTo({ top: 1400, behavior: "instant" })
})
await page.waitForTimeout(900)
await page.screenshot({ path: `${out}\\assembly-field-scrolled.png` })
const fadedOpacity = await page.locator("canvas.asm-field-canvas").evaluate((node) => {
  return Number.parseFloat(getComputedStyle(node).opacity)
})

// Mobile layout, no camera.
const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } })
watch(mobile)
await mobile.goto(base, { waitUntil: "networkidle" })
await mobile.waitForTimeout(2500)
await mobile.screenshot({ path: `${out}\\assembly-field-mobile-raw.png`, fullPage: false })
await dismissCookie(mobile)
await mobile.screenshot({ path: `${out}\\assembly-field-mobile.png`, fullPage: false })
await mobile.locator(".asm-camera-toggle").scrollIntoViewIfNeeded()
await mobile.waitForTimeout(600)
await mobile.screenshot({ path: `${out}\\assembly-field-mobile-camera.png`, fullPage: false })

console.log(
  JSON.stringify(
    {
      errors,
      fadedOpacity,
      screenshots: out,
    },
    null,
    2,
  ),
)
await browser.close()
